"""
Unit 1.12 done criteria: compute_beat_lock() against a synthetic beat grid
and cuts deliberately offset by a known amount. This test specifically
guards the "don't snap to zero" regression called out repeatedly in
signals/audio.py's docstrings - editors habitually cut 1-3 frames BEFORE
the beat, and that sign/magnitude must survive into median_cut_offset_frames.
"""

from __future__ import annotations

from signals.audio import compute_beat_lock

FPS = 30
BEAT_GRID = [0.0, 0.5, 1.0, 1.5]


def test_median_offset_is_negative_not_zero_for_early_cuts() -> None:
    # 0.48s -> nearest beat 0.5s -> offset (0.48-0.5)*30 = -0.6 -> round -1
    # 0.97s -> nearest beat 1.0s -> offset (0.97-1.0)*30 = -0.9 -> round -1
    cut_times = [0.48, 0.97]
    beat_lock_ratio, median_offset = compute_beat_lock(cut_times, BEAT_GRID, fps=FPS)

    assert median_offset == -1
    assert median_offset != 0, "regression guard: median offset must NOT collapse to zero"
    assert beat_lock_ratio == 1.0


def test_nonzero_offset_differs_from_naive_on_beat_snapping() -> None:
    # A cut exactly ON the beat (offset 0) vs the same grid shifted early by
    # 1 frame - the two results must differ, guarding against a "simplified"
    # implementation that always snaps to the beat itself (offset 0).
    on_beat_ratio, on_beat_median = compute_beat_lock([0.5, 1.0], BEAT_GRID, fps=FPS)
    early_ratio, early_median = compute_beat_lock([0.48, 0.97], BEAT_GRID, fps=FPS)

    assert on_beat_median == 0
    assert early_median == -1
    assert on_beat_median != early_median


def test_cuts_with_no_nearby_beat_excluded_from_median_but_counted_in_ratio() -> None:
    # 5.0s is far from every beat in BEAT_GRID (max 1.5s) - doesn't lock.
    cut_times = [0.48, 0.97, 5.0]
    beat_lock_ratio, median_offset = compute_beat_lock(cut_times, BEAT_GRID, fps=FPS)

    assert beat_lock_ratio == 2 / 3  # 2 of 3 cuts locked
    assert median_offset == -1  # median over the 2 LOCKED cuts only, unaffected by the far-away one


def test_empty_inputs_return_zero() -> None:
    assert compute_beat_lock([], BEAT_GRID, fps=FPS) == (0.0, 0)
    assert compute_beat_lock([0.5], [], fps=FPS) == (0.0, 0)
