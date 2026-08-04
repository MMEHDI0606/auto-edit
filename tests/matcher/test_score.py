"""
Unit 3.7 done criteria: a hand-constructed asset/requirements pair that
should obviously score high (matching everything) and one that should
score low (mismatched on every dimension) - confirm the ordering is right,
not chasing a specific numeric value yet (tuning against human ratings is
Unit 3.9's job).

Most tests here set `requirements.role = None` so the (expensive) CLIP
text-encoder path is never touched - `_clip_similarity_to_role_exemplar`
short-circuits to a constant 0.5 for a role-less slot, keeping the
face/shot_type/motion sub-scores independently testable without a model
load. The handful of tests that DO need real CLIP similarity are marked
`slow`.
"""

from __future__ import annotations

import numpy as np
import pytest

from matcher.probe import AssetFeatures
from matcher.score import SCORE_WEIGHTS, _clip_similarity_to_role_exemplar, cost_matrix, score_pair
from schemas.models import SlotRequirements


def _asset(**overrides) -> AssetFeatures:
    defaults = dict(
        asset_id="a1",
        asset_path="/fake/a1.mp4",
        duration_s=5.0,
        orientation="vertical",
        has_face=False,
        shot_type_guess="wide",
        motion_score=0.0,
        clip_embedding=[0.0] * 512,
        has_speech=False,
    )
    defaults.update(overrides)
    return AssetFeatures(**defaults)


def test_score_weights_sum_to_one() -> None:
    assert sum(SCORE_WEIGHTS.values()) == pytest.approx(1.0)


def test_face_match_scores_higher_when_face_required_and_present() -> None:
    requirements = SlotRequirements(needs_face=True, role=None)
    with_face = score_pair(_asset(has_face=True), requirements)
    without_face = score_pair(_asset(has_face=False), requirements)
    assert with_face > without_face


def test_face_match_is_neutral_when_not_required() -> None:
    requirements = SlotRequirements(needs_face=False, role=None)
    # Neither penalized nor rewarded for having a face when there's no constraint.
    assert score_pair(_asset(has_face=True), requirements) == score_pair(_asset(has_face=False), requirements)


def test_shot_type_match_scores_higher_when_preferred_type_present() -> None:
    requirements = SlotRequirements(shot_type_pref=["closeup"], role=None)
    matching = score_pair(_asset(shot_type_guess="closeup"), requirements)
    mismatched = score_pair(_asset(shot_type_guess="wide"), requirements)
    assert matching > mismatched


def test_shot_type_match_is_full_credit_when_pref_list_empty() -> None:
    requirements = SlotRequirements(shot_type_pref=[], role=None)
    assert score_pair(_asset(shot_type_guess="wide"), requirements) == score_pair(
        _asset(shot_type_guess="closeup"), requirements
    )


def test_motion_pref_match_scores_higher_when_bucket_matches() -> None:
    requirements = SlotRequirements(motion_pref="high", role=None)
    high_motion = score_pair(_asset(motion_score=0.5), requirements)
    low_motion = score_pair(_asset(motion_score=0.0), requirements)
    assert high_motion > low_motion


def test_clip_similarity_is_neutral_when_slot_has_no_role() -> None:
    # role=None must short-circuit WITHOUT loading CLIP - this test would
    # take ~seconds instead of milliseconds if it accidentally did.
    assert _clip_similarity_to_role_exemplar([0.0] * 512, None) == 0.5


def test_cost_matrix_shape_and_is_one_minus_score() -> None:
    assets = [_asset(asset_id="a1"), _asset(asset_id="a2", has_face=True)]
    requirements = [SlotRequirements(needs_face=True, role=None), SlotRequirements(needs_face=False, role=None)]

    matrix = cost_matrix(assets, requirements)

    assert len(matrix) == 2
    assert len(matrix[0]) == 2
    for i, asset in enumerate(assets):
        for j, req in enumerate(requirements):
            assert matrix[i][j] == pytest.approx(1.0 - score_pair(asset, req))


# --------------------------------------------------------------------------
# Real CLIP text-encoder tests (slow - loads model weights)
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_score_pair_ranks_an_all_around_match_above_an_all_around_mismatch() -> None:
    from matcher.score import _role_exemplar_embedding

    hook_embedding = _role_exemplar_embedding("hook")
    # An embedding orthogonal-ish to the "hook" exemplar - a unit vector
    # pointed at a different axis gives a real, low (not just hand-typed)
    # cosine similarity against it.
    unrelated = np.zeros(len(hook_embedding))
    unrelated[-1] = 1.0
    unrelated = unrelated.tolist()

    requirements = SlotRequirements(needs_face=True, shot_type_pref=["closeup"], motion_pref="high", role="hook")
    good_asset = _asset(
        has_face=True, shot_type_guess="closeup", motion_score=0.5, clip_embedding=hook_embedding
    )
    bad_asset = _asset(
        has_face=False, shot_type_guess="wide", motion_score=0.0, clip_embedding=unrelated
    )

    assert score_pair(good_asset, requirements) > score_pair(bad_asset, requirements)


@pytest.mark.slow
def test_clip_similarity_to_role_exemplar_is_near_one_for_its_own_exemplar() -> None:
    from matcher.score import _role_exemplar_embedding

    embedding = _role_exemplar_embedding("reveal")
    assert _clip_similarity_to_role_exemplar(embedding, "reveal") == pytest.approx(1.0, abs=1e-4)


@pytest.mark.slow
def test_unrecognized_role_still_produces_a_valid_similarity_score() -> None:
    unit_vector = (np.ones(512) / np.linalg.norm(np.ones(512))).tolist()
    similarity = _clip_similarity_to_role_exemplar(unit_vector, "some_unrecognized_role")
    assert 0.0 <= similarity <= 1.0
