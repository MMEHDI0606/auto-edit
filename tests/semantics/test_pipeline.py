"""
Unit 3.4 - deep-pass trigger policy (semantics/pipeline.py::needs_deep_pass).
Lives outside AnthropicProvider on purpose (see that module's docstring) -
tested standalone against hand-built Shot objects, no provider involved.
"""

from __future__ import annotations

from schemas.models import MotionCurve, MotionPrimitive, Shot, ShotContent, Transition, TransitionType
from semantics.pipeline import needs_deep_pass
from signals.motion import FIT_RESIDUAL_THRESHOLD


def _shot(*, residual: float, shot_type: str | None) -> Shot:
    return Shot(
        id="shot1",
        t_in=0.0,
        t_out=1.0,
        in_transition=Transition(type=TransitionType.cut),
        out_transition=Transition(type=TransitionType.cut),
        motion=MotionCurve(primitive=MotionPrimitive.static, residual=residual),
        content=ShotContent(shot_type=shot_type),
    )


def test_needs_deep_pass_true_when_residual_above_keyframe_threshold() -> None:
    shot = _shot(residual=FIT_RESIDUAL_THRESHOLD + 0.01, shot_type="wide")
    assert needs_deep_pass(shot) is True


def test_needs_deep_pass_true_when_shot_type_unset() -> None:
    shot = _shot(residual=0.0, shot_type=None)
    assert needs_deep_pass(shot) is True


def test_needs_deep_pass_false_when_confidence_is_high_and_no_role_needed() -> None:
    shot = _shot(residual=0.0, shot_type="wide")
    assert needs_deep_pass(shot) is False


def test_needs_deep_pass_true_when_role_label_explicitly_requested() -> None:
    shot = _shot(residual=0.0, shot_type="wide")
    assert needs_deep_pass(shot, needs_role_label=True) is True
