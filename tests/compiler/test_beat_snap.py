"""
Unit 2.2 done criteria: snap_duration_to_beat() against a synthetic beat
grid - a window that contains a valid beat (assert snapped, correct
duration), one that doesn't (assert unsnapped fallback), and a check that
a nonzero median_cut_offset_frames actually shifts the result versus an
offset of 0 (guard against collapsing to naive on-beat snapping).
"""

from __future__ import annotations

from compiler.beat_snap import snap_duration_to_beat

FPS = 30
BEAT_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]


def test_snaps_to_beat_within_window() -> None:
    # window [0.8, 1.2] contains beat at 1.0
    duration, was_snapped = snap_duration_to_beat(
        min_s=0.8, max_s=1.2, nominal_s=1.0, t_start_s=0.0,
        beat_grid_s=BEAT_GRID, median_cut_offset_frames=0, fps=FPS,
    )
    assert was_snapped is True
    assert duration == 1.0  # beat at 1.0 - offset(0) - t_start(0)


def test_falls_back_when_no_beat_in_window() -> None:
    # window [0.1, 0.3] contains no beat at all (nearest beats are 0.0, 0.5)
    duration, was_snapped = snap_duration_to_beat(
        min_s=0.1, max_s=0.3, nominal_s=0.2, t_start_s=0.0,
        beat_grid_s=BEAT_GRID, median_cut_offset_frames=0, fps=FPS,
    )
    assert was_snapped is False
    assert duration == 0.2  # nominal, unchanged


def test_nonzero_offset_shifts_result_away_from_naive_on_beat_snapping() -> None:
    # Same window/beat as the zero-offset case, but a -2 frame offset
    # (editors cut slightly early) must shift the result measurably -
    # this is the regression guard against "just snap to the beat exactly."
    common_kwargs = dict(
        min_s=0.8, max_s=1.2, nominal_s=1.0, t_start_s=0.0, beat_grid_s=BEAT_GRID, fps=FPS,
    )
    duration_zero_offset, _ = snap_duration_to_beat(median_cut_offset_frames=0, **common_kwargs)
    duration_neg_offset, _ = snap_duration_to_beat(median_cut_offset_frames=-2, **common_kwargs)

    assert duration_zero_offset != duration_neg_offset
    expected_shift = 2 / FPS
    assert duration_neg_offset == duration_zero_offset + expected_shift


def test_picks_closest_candidate_beat_to_nominal_duration() -> None:
    # window [0.4, 2.6] contains beats at 0.5, 1.0, 1.5, 2.0, 2.5 - nominal
    # duration 1.5 should pick the beat giving a candidate_duration closest
    # to 1.5, i.e. beat at 1.5 itself (offset 0).
    duration, was_snapped = snap_duration_to_beat(
        min_s=0.4, max_s=2.6, nominal_s=1.5, t_start_s=0.0,
        beat_grid_s=BEAT_GRID, median_cut_offset_frames=0, fps=FPS,
    )
    assert was_snapped is True
    assert duration == 1.5


def test_empty_beat_grid_falls_back() -> None:
    duration, was_snapped = snap_duration_to_beat(
        min_s=0.5, max_s=1.5, nominal_s=1.0, t_start_s=0.0,
        beat_grid_s=[], median_cut_offset_frames=0, fps=FPS,
    )
    assert was_snapped is False
    assert duration == 1.0
