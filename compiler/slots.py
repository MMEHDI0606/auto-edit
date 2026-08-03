"""
L3 - converts each Shot (+ optional SemanticShotAnnotation) into a Slot.
See RECUT_SPEC.md sec 5.1.

`human_instruction` generation is THE product surface (spec's own words:
"the human_instruction field is the product") - treat wording quality as a
first-class deliverable, not boilerplate string formatting. In Phase 1-2
(before L2 semantics exist), generate a mechanical instruction from L1
facts alone (duration, motion_pref, needs_face); in Phase 3, prefer the
LLM-authored version when semantics are available, still constrained to
only reference evidence-backed facts (same evidence-gating principle as
L2 - see semantics/gating.py).
"""

from __future__ import annotations

from schemas.models import SemanticShotAnnotation, Shot, Slot


def shot_to_slot(shot: Shot, order: int, *, annotation: SemanticShotAnnotation | None = None) -> Slot:
    raise NotImplementedError


def generate_human_instruction(shot: Shot, *, annotation: SemanticShotAnnotation | None = None) -> str:
    """Mechanical (L1-only) instruction when annotation is None; richer
    phrasing when semantic role/content is available. Must never state a
    fact not backed by shot.effects/motion/content - same rule as L2."""
    raise NotImplementedError


def derive_duration_flex(shot: Shot, *, beat_grid_s: list[float]) -> dict:
    """min_s/max_s bounds and snap policy. See compiler/beat_snap.py for
    the actual snapping algorithm consumed by the matcher - this function
    only decides the flex WINDOW, not how a bound asset's cut point gets
    snapped at match time."""
    raise NotImplementedError
