"""
Unit 3.1 done criteria: the evidence gate is built and unit-tested BEFORE
any provider exists (Unit 3.3), against synthetic model output - so the
"VLM invents effects" failure mode (spec sec 8.3) is caught here, not
discovered later against a real (expensive, slow) model call.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from schemas.models import (
    AudioTrace,
    EditTrace,
    EffectType,
    EvidenceMeta,
    MotionCurve,
    MotionPrimitive,
    SemanticShotAnnotation,
    Shot,
    ShotEffect,
    SourceInfo,
    Transition,
    TransitionType,
)
from semantics.gating import EvidenceViolation, allowed_labels_for_shot, repair_or_fail, validate_annotation


def _make_shot(shot_id: str = "shot1") -> Shot:
    """Only a freeze effect, static motion, hard cuts on both sides -
    deliberately narrow evidence set (per Unit 3.1's own done criteria)."""
    return Shot(
        id=shot_id,
        t_in=0.0,
        t_out=1.0,
        in_transition=Transition(type=TransitionType.cut),
        out_transition=Transition(type=TransitionType.cut),
        motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01),
        effects=[ShotEffect(type=EffectType.freeze, params={})],
    )


def _make_trace(shot: Shot) -> EditTrace:
    return EditTrace(
        source=SourceInfo(hash="abc123", duration_s=10.0, fps=30, w=1080, h=1920),
        audio=AudioTrace(),
        shots=[shot],
        evidence=EvidenceMeta(cut_detector="adaptive+content", ocr_fps=2, flow_method="farneback"),
    )


def test_allowed_labels_for_shot_is_the_union_of_effects_transitions_and_motion() -> None:
    trace = _make_trace(_make_shot())
    assert allowed_labels_for_shot(trace, "shot1") == {"freeze", "cut", "static"}


def test_allowed_labels_for_shot_raises_for_unknown_shot_id() -> None:
    trace = _make_trace(_make_shot())
    with pytest.raises(ValueError):
        allowed_labels_for_shot(trace, "nonexistent")


def test_validate_annotation_passes_through_evidence_backed_claims_unchanged() -> None:
    allowed = {"freeze", "cut", "static"}
    annotation = SemanticShotAnnotation(
        shot_id="shot1", role="freeze-frame hook", role_confidence=0.8, model_id="test-model"
    )
    result = validate_annotation(annotation, allowed)
    assert result is annotation
    assert result.role == "freeze-frame hook"


def test_validate_annotation_passes_through_ordinary_descriptive_role_with_no_claims() -> None:
    allowed = {"freeze", "cut", "static"}
    annotation = SemanticShotAnnotation(shot_id="shot1", role="reaction", role_confidence=0.6, model_id="test-model")
    assert validate_annotation(annotation, allowed) is annotation


def test_validate_annotation_raises_on_unlicensed_effect_claim() -> None:
    """A shot with ONLY a freeze effect (see _make_shot) - if the model's
    role claims an rgb_split, that's an evidence violation: rgb_split was
    never detected on this shot."""
    trace = _make_trace(_make_shot())
    allowed = allowed_labels_for_shot(trace, "shot1")
    annotation = SemanticShotAnnotation(
        shot_id="shot1", role="glitchy rgb_split reveal", role_confidence=0.9, model_id="test-model"
    )
    with pytest.raises(EvidenceViolation):
        validate_annotation(annotation, allowed)


def test_validate_annotation_raises_on_unlicensed_transition_claim() -> None:
    trace = _make_trace(_make_shot())
    allowed = allowed_labels_for_shot(trace, "shot1")
    annotation = SemanticShotAnnotation(
        shot_id="shot1", role="dissolve into next scene", role_confidence=0.7, model_id="test-model"
    )
    with pytest.raises(EvidenceViolation):
        validate_annotation(annotation, allowed)


def test_validate_annotation_raises_on_unlicensed_motion_primitive_claim() -> None:
    trace = _make_trace(_make_shot())
    allowed = allowed_labels_for_shot(trace, "shot1")
    annotation = SemanticShotAnnotation(
        shot_id="shot1", role="fast whip motion", role_confidence=0.7, model_id="test-model"
    )
    with pytest.raises(EvidenceViolation):
        validate_annotation(annotation, allowed)


def test_validate_annotation_no_role_is_a_noop() -> None:
    annotation = SemanticShotAnnotation(shot_id="shot1", role=None, model_id="test-model")
    assert validate_annotation(annotation, set()) is annotation


# --------------------------------------------------------------------------
# Unit 3.4 - repair_or_fail(): "one repair retry, then fail loudly" (spec 4.3)
# --------------------------------------------------------------------------


class _DummySchema(BaseModel):
    role: str | None = None
    role_confidence: float = 0.0


def test_repair_or_fail_returns_dict_on_first_valid_response() -> None:
    def retry_fn(_error: str) -> str:
        raise AssertionError("retry_fn must not be called when the first response is already valid")

    result = repair_or_fail('{"role": "hook", "role_confidence": 0.8}', _DummySchema, retry_fn=retry_fn)
    assert result == {"role": "hook", "role_confidence": 0.8}


def test_repair_or_fail_retries_once_and_succeeds() -> None:
    calls: list[str] = []

    def retry_fn(error_message: str) -> str:
        calls.append(error_message)
        return '{"role": "reveal", "role_confidence": 0.6}'

    result = repair_or_fail("not json at all", _DummySchema, retry_fn=retry_fn)

    assert result == {"role": "reveal", "role_confidence": 0.6}
    assert len(calls) == 1
    assert calls[0]  # the validation error message was actually passed through


def test_repair_or_fail_raises_after_second_failure() -> None:
    def retry_fn(_error: str) -> str:
        return "still not json"

    with pytest.raises(ValidationError):
        repair_or_fail("not json at all", _DummySchema, retry_fn=retry_fn)


# --------------------------------------------------------------------------
# Unit 3.4 done criteria: deep_pass() -> validate_annotation() end-to-end.
# A shot with only a freeze effect (narrow evidence, see _make_shot) must
# never end up with a persisted annotation claiming an unlicensed effect -
# either the model's claim is evidence-compliant and passes, or it isn't
# and EvidenceViolation is raised (never silently passed through).
# --------------------------------------------------------------------------


def test_deep_pass_output_that_is_evidence_compliant_passes_validation() -> None:
    trace = _make_trace(_make_shot())
    allowed = allowed_labels_for_shot(trace, "shot1")
    # Simulates a deep_pass() result that only claims what the shot's own
    # evidence licenses (freeze, a real effect on this shot).
    annotation = SemanticShotAnnotation(
        shot_id="shot1", role="freeze-frame hook", role_confidence=0.85, model_id="claude-sonnet-5"
    )
    assert validate_annotation(annotation, allowed) is annotation


def test_deep_pass_output_that_invents_an_effect_is_caught_not_silently_passed_through() -> None:
    trace = _make_trace(_make_shot())
    allowed = allowed_labels_for_shot(trace, "shot1")
    # Simulates a deep_pass() result where the model ignored the prompt's
    # allowed_effect_labels instruction and hallucinated rgb_split anyway -
    # gating.py is the second, code-level enforcement layer for exactly
    # this failure mode (spec sec 8.3).
    annotation = SemanticShotAnnotation(
        shot_id="shot1", role="rgb_split glitch reveal", role_confidence=0.9, model_id="claude-sonnet-5"
    )
    with pytest.raises(EvidenceViolation):
        validate_annotation(annotation, allowed)
