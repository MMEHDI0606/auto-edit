"""
L3/L4 shared algorithm, split into its own module because the original
spec left it implicit ("snap to the beat grid" appears in both sec 5.1
duration_flex.snap and sec 6 step 4, without defining the algorithm - see
DESIGN_NOTES.md "Beat-snap needs one definition, not two").

Definition (binding for compiler/ and matcher/ alike):
  Given a slot's [min_s, max_s] duration window, the source beat_grid_s,
  and the trace's median_cut_offset_frames (signed, usually negative -
  editors cut slightly early, see signals/audio.py), the snapped duration is
  the one that lands the OUT point at:
      nearest_beat_time - (median_cut_offset_frames / fps)
  clamped to [min_s, max_s]. If no beat falls within the window, fall back
  to the raw (unsnapped) duration and set a confidence flag - do not snap
  to a beat outside the allowed window just to force alignment.
"""

from __future__ import annotations


def snap_duration_to_beat(
    *,
    min_s: float,
    max_s: float,
    nominal_s: float,
    t_start_s: float,
    beat_grid_s: list[float],
    median_cut_offset_frames: int,
    fps: int,
) -> tuple[float, bool]:
    """Returns (snapped_duration_s, was_snapped). See module docstring for
    the exact definition - implement to that spec, do not re-derive it."""
    window_start = t_start_s + min_s
    window_end = t_start_s + max_s
    candidate_beats = [b for b in beat_grid_s if window_start <= b <= window_end]
    if not candidate_beats:
        return nominal_s, False

    offset_s = median_cut_offset_frames / fps
    best_duration = nominal_s
    best_diff = float("inf")
    for beat_time in candidate_beats:
        candidate_duration = beat_time - offset_s - t_start_s
        diff = abs(candidate_duration - nominal_s)
        if diff < best_diff:
            best_diff = diff
            best_duration = candidate_duration

    return best_duration, True
