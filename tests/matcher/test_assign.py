"""
Unit 3.8 - matcher/assign.py::pick_in_point() and match_assets().

pick_in_point tests exercise real cv2 frame-seeking against the existing
Phase-1 synthetic_clip.mp4 fixture - no ML models involved, but the
0.1s-step sliding window scan over a real file is real wall-clock work
(hundreds of cv2 seek/decode calls per pick_in_point() call), so these are
marked slow alongside the model-loading tests elsewhere, to keep the
default `-m "not slow"` suite fast.
match_assets tests use role=None throughout (so score_pair's CLIP path
never loads a model - see tests/matcher/test_score.py's own note on this)
and point every hand-built AssetFeatures at one of the two existing real
fixture videos, so pick_in_point's real cv2 seeking still gets exercised
inside match_assets without needing 5-8 actually-distinct video files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matcher.assign import CONFIDENCE_FLOOR, match_assets, pick_in_point
from matcher.probe import AssetFeatures
from schemas.models import (
    AudioRef,
    DurationFlex,
    MotionCurve,
    MotionPrimitive,
    Slot,
    SlotApplied,
    SlotRequirements,
    Template,
)

FACE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_face_clip.mp4"
NO_FACE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


def _asset(asset_id: str, path: Path, **overrides) -> AssetFeatures:
    defaults = dict(
        asset_path=str(path),
        duration_s=3.5,
        orientation="vertical",
        has_face=False,
        shot_type_guess="wide",
        motion_score=0.0,
        clip_embedding=[0.0] * 512,
        has_speech=False,
    )
    defaults.update(overrides)
    return AssetFeatures(asset_id=asset_id, **defaults)


def _slot(slot_id: str, order: int, duration_s: float, requirements: SlotRequirements) -> Slot:
    return Slot(
        slot_id=slot_id,
        order=order,
        duration_s=duration_s,
        duration_flex=DurationFlex(min_s=duration_s * 0.75, max_s=duration_s * 1.25, snap="none"),
        requirements=requirements,
        applied=SlotApplied(motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01)),
        human_instruction="test slot",
    )


def _template(slots: list[Slot], *, beat_grid_s: list[float] | None = None) -> Template:
    return Template(
        source_trace_hash="deadbeef",
        source_fps=30,
        slots=slots,
        audio_ref=AudioRef(beat_grid_s=beat_grid_s or []),
    )


# --------------------------------------------------------------------------
# pick_in_point
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_pick_in_point_returns_a_valid_start_within_bounds() -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")
    asset = _asset("a1", NO_FACE_FIXTURE, duration_s=3.5)

    in_point = pick_in_point(asset, required_duration_s=1.0)

    assert 0.0 <= in_point <= asset.duration_s - 1.0


@pytest.mark.slow
def test_pick_in_point_is_deterministic() -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")
    asset = _asset("a1", NO_FACE_FIXTURE, duration_s=3.5)

    first = pick_in_point(asset, required_duration_s=1.0)
    second = pick_in_point(asset, required_duration_s=1.0)
    assert first == second


@pytest.mark.slow
def test_pick_in_point_returns_zero_when_required_duration_covers_whole_asset() -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")
    asset = _asset("a1", NO_FACE_FIXTURE, duration_s=3.5)

    assert pick_in_point(asset, required_duration_s=3.5) == 0.0


# --------------------------------------------------------------------------
# match_assets
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_match_assets_prefers_a_face_asset_for_a_face_requiring_slot() -> None:
    if not (FACE_FIXTURE.exists() and NO_FACE_FIXTURE.exists()):
        pytest.skip("run tests/fixtures/make_face_clip.py and make_synthetic_clip.py first")

    assets = [
        _asset("face1", FACE_FIXTURE, has_face=True, shot_type_guess="closeup", motion_score=0.09, duration_s=5.19),
        _asset("plain1", NO_FACE_FIXTURE, has_face=False, shot_type_guess="wide", motion_score=0.0),
        _asset("plain2", NO_FACE_FIXTURE, has_face=False, shot_type_guess="wide", motion_score=0.0),
        _asset("plain3", NO_FACE_FIXTURE, has_face=False, shot_type_guess="wide", motion_score=0.0),
        _asset("plain4", NO_FACE_FIXTURE, has_face=False, shot_type_guess="wide", motion_score=0.0),
    ]

    template = _template(
        [
            _slot("slot_01", 1, 1.0, SlotRequirements(needs_face=True, shot_type_pref=["closeup"], motion_pref="high")),
            _slot("slot_02", 2, 0.8, SlotRequirements(needs_face=False, shot_type_pref=["wide"], motion_pref="low")),
            _slot("slot_03", 3, 0.8, SlotRequirements(needs_face=False, shot_type_pref=["wide"], motion_pref="low")),
            # Deliberately unsatisfiable: needs a face (none left after
            # slot_01 takes the only one, max_reuse=1) AND mismatches
            # shot_type/motion against every remaining (plain) asset, so
            # every candidate's score falls below CONFIDENCE_FLOOR.
            _slot(
                "slot_04",
                4,
                1.0,
                SlotRequirements(needs_face=True, shot_type_pref=["extreme_wide"], motion_pref="medium"),
            ),
        ]
    )

    result = match_assets(template, assets, max_reuse=1)

    binding_by_slot = {b.slot_id: b for b in result.bindings}
    assert binding_by_slot["slot_01"].asset_id == "face1"
    assert "slot_04" in result.unresolved_slots
    assert "slot_04" not in binding_by_slot

    # No asset used more than max_reuse=1 times.
    used_asset_ids = [b.asset_id for b in result.bindings]
    assert len(used_asset_ids) == len(set(used_asset_ids))

    for binding in result.bindings:
        assert binding.rationale  # never empty
        assert binding.confidence >= CONFIDENCE_FLOOR


@pytest.mark.slow
def test_match_assets_never_reuses_an_asset_beyond_max_reuse_count() -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    # Only ONE real asset available, but three slots want it - max_reuse=2
    # means at most 2 of those 3 slots may be filled by it; the third must
    # go unresolved rather than tripling up on the same asset.
    assets = [_asset("only_asset", NO_FACE_FIXTURE, shot_type_guess="wide", motion_score=0.0)]
    requirements = SlotRequirements(needs_face=False, shot_type_pref=["wide"], motion_pref="low")
    template = _template([_slot(f"slot_0{i}", i, 0.8, requirements) for i in (1, 2, 3)])

    result = match_assets(template, assets, max_reuse=2)

    assert len(result.bindings) == 2
    assert len(result.unresolved_slots) == 1
    assert all(b.asset_id == "only_asset" for b in result.bindings)


def test_match_assets_with_no_assets_puts_every_slot_in_unresolved() -> None:
    template = _template([_slot("slot_01", 1, 1.0, SlotRequirements())])
    result = match_assets(template, [], max_reuse=2)
    assert result.bindings == []
    assert result.unresolved_slots == ["slot_01"]


@pytest.mark.slow
def test_match_assets_binding_duration_defaults_to_nominal_when_no_beat_grid() -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    assets = [_asset("a1", NO_FACE_FIXTURE, shot_type_guess="wide", motion_score=0.0)]
    template = _template([_slot("slot_01", 1, 1.0, SlotRequirements())], beat_grid_s=[])

    result = match_assets(template, assets, max_reuse=1)

    assert len(result.bindings) == 1
    # No beat grid at all -> snap_duration_to_beat falls back to the
    # nominal duration unchanged (compiler/beat_snap.py's own contract).
    assert result.bindings[0].duration_s == pytest.approx(1.0)
