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

import numpy as np
import torch

from matcher.probe import AssetFeatures, get_clip_model
from schemas.models import SlotRequirements

SCORE_WEIGHTS = {
    "clip_similarity": 0.40,
    "face_match": 0.25,
    "shot_type_match": 0.20,
    "motion_pref_match": 0.15,
}

# Bootstrapped against CLIP's own text encoder (no curated exemplar image
# set exists yet) - a short natural-language description per common role,
# per Unit 3.7's own suggested shortcut. Retune/expand against the golden
# set once real human A/B ratings exist; these are starting points.
_ROLE_EXEMPLAR_PROMPTS: dict[str, str] = {
    "hook": "an attention-grabbing opening shot of a short-form video",
    "before_state": "a plain 'before' shot showing an unremarkable starting state",
    "reveal": "a dramatic reveal or transformation moment",
    "reaction": "a close-up reaction shot of a person's face",
    "cta": "a call-to-action shot of a person gesturing to follow or subscribe",
}

# Asset motion_score (frame-diff energy, roughly [0, 1] - see matcher/probe.py)
# bucketed into the same low/medium/high vocabulary as SlotRequirements.motion_pref.
# Starting thresholds, not tuned against real footage yet.
_MOTION_LOW_THRESHOLD = 0.02
_MOTION_HIGH_THRESHOLD = 0.08

_role_exemplar_cache: dict[str, list[float]] = {}


def _role_exemplar_embedding(role: str) -> list[float]:
    if role not in _role_exemplar_cache:
        model, _preprocess, tokenizer = get_clip_model()
        prompt = _ROLE_EXEMPLAR_PROMPTS.get(role, f"a video shot depicting {role.replace('_', ' ')}")
        tokens = tokenizer([prompt])
        with torch.no_grad():
            features = model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
        _role_exemplar_cache[role] = features.squeeze(0).tolist()
    return _role_exemplar_cache[role]


def _clip_similarity_to_role_exemplar(clip_embedding: list[float], role: str | None) -> float:
    if not role:
        return 0.5  # no role constraint on this slot - neither rewarded nor penalized
    exemplar = _role_exemplar_embedding(role)
    cosine_similarity = float(np.dot(clip_embedding, exemplar))
    # both vectors are L2-normalized (probe.py, _role_exemplar_embedding),
    # so this is a true cosine similarity in [-1, 1] - rescale to [0, 1] to
    # match this scoring function's convention for every other term.
    return (cosine_similarity + 1.0) / 2.0


def _face_match(asset: AssetFeatures, requirements: SlotRequirements) -> float:
    if not requirements.needs_face:
        return 0.5  # no constraint either way
    return 1.0 if asset.has_face else 0.0


def _shot_type_match(asset: AssetFeatures, requirements: SlotRequirements) -> float:
    if not requirements.shot_type_pref or asset.shot_type_guess in requirements.shot_type_pref:
        return 1.0
    return 0.5  # partial credit - shot-type guesses are approximate on both sides, not a hard 0


def _asset_motion_bucket(motion_score: float) -> str:
    if motion_score < _MOTION_LOW_THRESHOLD:
        return "low"
    if motion_score < _MOTION_HIGH_THRESHOLD:
        return "medium"
    return "high"


def _motion_pref_match(asset: AssetFeatures, requirements: SlotRequirements) -> float:
    if requirements.motion_pref is None:
        return 1.0  # no constraint
    return 1.0 if _asset_motion_bucket(asset.motion_score) == requirements.motion_pref else 0.5


def score_pair(asset: AssetFeatures, requirements: SlotRequirements) -> float:
    """Returns a score in [0, 1]; higher is better. See module docstring
    for the weighted-term definition this must implement."""
    return (
        SCORE_WEIGHTS["clip_similarity"] * _clip_similarity_to_role_exemplar(asset.clip_embedding, requirements.role)
        + SCORE_WEIGHTS["face_match"] * _face_match(asset, requirements)
        + SCORE_WEIGHTS["shot_type_match"] * _shot_type_match(asset, requirements)
        + SCORE_WEIGHTS["motion_pref_match"] * _motion_pref_match(asset, requirements)
    )


def cost_matrix(assets: list[AssetFeatures], all_requirements: list[SlotRequirements]) -> list[list[float]]:
    """Builds the (1 - score) cost matrix consumed by assign.py's Hungarian
    solver."""
    return [[1.0 - score_pair(asset, requirements) for requirements in all_requirements] for asset in assets]
