"""
L4 - scoring function for (asset, slot) pairs. See RECUT_SPEC.md sec 6,
step 3.

UNDERSPECIFIED IN THE ORIGINAL SPEC (see DESIGN_NOTES.md "Matcher scoring
needs explicit weights"): the spec names the inputs (CLIP embedding,
face/shot-type/motion score) and the solver (Hungarian) but never defines
how those inputs combine into one scalar cost. This module owns that
definition so it's a tunable, tested function rather than ad hoc code
buried inside assign.py.

Starting weights (tune against the golden set's human A/B ratings, do not
treat as final):
    score = 0.4 * clip_similarity_to_role_exemplar
          + 0.25 * face_requirement_match      (1.0 if needs_face satisfied, 0.0 if violated, 0.5 if unknown)
          + 0.20 * shot_type_match
          + 0.15 * motion_pref_match
Each term is in [0, 1]; the assignment solver minimizes (1 - score) as cost.
"""

from __future__ import annotations

from matcher.probe import AssetFeatures
from schemas.models import SlotRequirements

SCORE_WEIGHTS = {
    "clip_similarity": 0.40,
    "face_match": 0.25,
    "shot_type_match": 0.20,
    "motion_pref_match": 0.15,
}


def score_pair(asset: AssetFeatures, requirements: SlotRequirements) -> float:
    """Returns a score in [0, 1]; higher is better. See module docstring
    for the weighted-term definition this must implement."""
    raise NotImplementedError


def cost_matrix(assets: list[AssetFeatures], all_requirements: list[SlotRequirements]) -> list[list[float]]:
    """Builds the (1 - score) cost matrix consumed by assign.py's Hungarian
    solver."""
    raise NotImplementedError
