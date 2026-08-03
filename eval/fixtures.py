"""
Synthetic fixtures for fast, deterministic unit tests - the fast tier of
the "two-tier eval" design (see eval/metrics.py docstring and
DESIGN_NOTES.md). Not in the original spec's repo layout; added because
the 30-video golden set (spec sec 12) is too slow/expensive to be the ONLY
test signal during day-to-day development of signals/ and compiler/.

Examples of what belongs here once Phase 1 starts:
  - a hand-built list of frame-diff spikes -> expected cuts.detect_cuts
    output, with no real video decoding involved
  - a synthetic (tx, ty, scale) series with a known easing curve ->
    expected motion.fit_motion_curve output
  - a synthetic beat grid + cut list -> expected audio.compute_beat_lock
    output, including a case with a nonzero median_cut_offset_frames to
    guard against the "snap to zero" regression called out in signals/audio.py
"""

from __future__ import annotations
