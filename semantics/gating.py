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

from schemas.models import EditTrace, SemanticShotAnnotation


class EvidenceViolation(Exception):
    """Raised (and caught, per-shot) when a model asserts a label with no
    supporting L1 evidence."""


def allowed_labels_for_shot(trace: EditTrace, shot_id: str) -> set[str]:
    """The enum of effect/role labels L1 evidence actually licenses for
    this shot - computed from Shot.effects, Shot.motion.primitive, and
    Shot.in_transition/out_transition. This is the allowlist a provider's
    output is checked against."""
    raise NotImplementedError


def validate_annotation(annotation: SemanticShotAnnotation, allowed: set[str]) -> SemanticShotAnnotation:
    """Strips/rejects any claim not licensed by `allowed`. Raises
    EvidenceViolation if the ENTIRE annotation is unusable (e.g. required
    role field asserts something evidence-incompatible); callers should
    catch this per-shot and fall back to an unlabeled/low-confidence
    annotation rather than failing the whole job.
    """
    raise NotImplementedError


def repair_or_fail(raw_model_output: str, schema, *, retry_fn) -> dict:
    """Validate raw_model_output against `schema`; on failure, call
    retry_fn once with a repair prompt; on second failure raise (fail
    loudly - spec sec 4.3, do not silently emit garbage)."""
    raise NotImplementedError
