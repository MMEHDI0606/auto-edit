"""
L2 - the evidence gate. This module is the literal enforcement of the
spec's core design rule (sec 1): "the LLM never measures... every semantic
claim in the output must be traceable to a numeric signal."

Concretely: before a provider is even called for a shot, compute the set of
labels L1 evidence permits (allowed_effect_labels). After the provider
responds, re-validate: any label in the response not in the allowed set is
a hallucination and must be dropped (with a logged warning), NOT silently
kept, and NOT used to fail the whole job - degrade gracefully per shot.

This module also owns the "one repair retry, then fail loudly" policy from
spec sec 4.3: if a provider's JSON fails schema validation, retry once with
a repair prompt; a second failure raises rather than emitting garbage.
"""

from __future__ import annotations

import re
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from schemas.models import EditTrace, EffectType, MotionPrimitive, SemanticShotAnnotation, TransitionType

_ModelT = TypeVar("_ModelT", bound=BaseModel)

# Every label string L2 could ever possibly assert, across all three
# evidence-bearing dimensions (effects / transitions / motion primitives).
# `allowed_labels_for_shot` narrows this to what one shot's Shot object
# actually licenses; `validate_annotation` checks a claim against that
# narrowed set, not this full set.
_ALL_EVIDENCE_LABELS: set[str] = (
    {e.value for e in EffectType} | {t.value for t in TransitionType} | {m.value for m in MotionPrimitive}
)


class EvidenceViolation(Exception):
    """Raised (and caught, per-shot) when a model asserts a label with no
    supporting L1 evidence."""


def allowed_labels_for_shot(trace: EditTrace, shot_id: str) -> set[str]:
    """The enum of effect/role labels L1 evidence actually licenses for
    this shot - computed from Shot.effects, Shot.motion.primitive, and
    Shot.in_transition/out_transition. This is the allowlist a provider's
    output is checked against."""
    shot = next((s for s in trace.shots if s.id == shot_id), None)
    if shot is None:
        raise ValueError(f"no shot with id {shot_id!r} in this trace")

    allowed: set[str] = {effect.type.value for effect in shot.effects}
    allowed.add(shot.in_transition.type.value)
    allowed.add(shot.out_transition.type.value)
    allowed.add(shot.motion.primitive.value)
    return allowed


def _asserted_labels(text: str) -> set[str]:
    """Which evidence labels does this free-text field assert, if any -
    matched as whole words/phrases (underscores treated as spaces) so
    "static" or "cut" appearing as an ordinary English word inside a longer
    unrelated word doesn't false-positive (e.g. "cutaway" != "cut")."""
    normalized = re.sub(r"[_\-]+", " ", text.lower())
    found = set()
    for label in _ALL_EVIDENCE_LABELS:
        phrase = label.replace("_", " ")
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            found.add(label)
    return found


def validate_annotation(annotation: SemanticShotAnnotation, allowed: set[str]) -> SemanticShotAnnotation:
    """Strips/rejects any claim not licensed by `allowed`. Raises
    EvidenceViolation if the ENTIRE annotation is unusable (e.g. required
    role field asserts something evidence-incompatible); callers should
    catch this per-shot and fall back to an unlabeled/low-confidence
    annotation rather than failing the whole job.

    v1's SemanticShotAnnotation only carries one free-text claim field
    (`role`) that could smuggle in an effect/transition/motion claim -
    checked here by scanning it for evidence-label words. `role` values
    that are ordinary descriptive words ("hook", "reaction") assert nothing
    and always pass through unchanged.
    """
    role = annotation.role
    if not role:
        return annotation

    asserted = _asserted_labels(role)
    unlicensed = asserted - allowed

    if unlicensed:
        raise EvidenceViolation(
            f"annotation for shot {annotation.shot_id!r} asserts label(s) {sorted(unlicensed)} "
            f"via role={role!r}, not licensed by this shot's evidence (allowed={sorted(allowed)})"
        )

    return annotation


def repair_or_fail(raw_model_output: str, schema: type[_ModelT], *, retry_fn: Callable[[str], str]) -> dict:
    """Validate raw_model_output against `schema`; on failure, call
    retry_fn once with a repair prompt; on second failure raise (fail
    loudly - spec sec 4.3, do not silently emit garbage).

    `retry_fn` receives the first attempt's validation error message (to be
    included in a repair prompt back to the model) and returns the new raw
    JSON text - it owns the actual re-call to the provider, this function
    only owns the validate/retry/fail POLICY, not the provider mechanics.
    """
    try:
        return schema.model_validate_json(raw_model_output).model_dump()
    except ValidationError as first_error:
        repaired_raw = retry_fn(str(first_error))
        try:
            return schema.model_validate_json(repaired_raw).model_dump()
        except ValidationError as second_error:
            raise second_error from first_error
