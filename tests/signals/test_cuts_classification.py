"""
Unit 1.5 done criteria: transition-type classification.

Covers the individual classification helpers against synthetic frame
arrays (fast, deterministic, no video decode) plus two end-to-end
detect_cuts() checks against real fixture videos:
  - synthetic_clip.mp4 (Unit 0.3/1.4): hard color-swap cuts only, no flash/
    whip/zoom/dissolve signal anywhere -> every boundary must classify as
    `cut`. This is the "classifier that labels everything cut" degenerate
    case guard IN REVERSE - confirms the classifier does NOT over-call a
    non-cut type when there's no evidence for one.
  - synthetic_flash_clip.mp4 (Unit 1.5, this file): a real luminance-spike
    transition -> at least one boundary must classify as something other
    than `cut`, confirming the classifier isn't defaulting to cut for
    everything either (the actual degenerate case INSTRUCTIONS.md Unit 1.5
    warns against).
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from schemas.models import TransitionType
from signals.cuts import (
    _check_dissolve,
    _check_whip_pan,
    _check_zoom_discontinuity,
    _hist_distance,
    detect_cuts,
)

SYNTHETIC_CLIP = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"
FLASH_CLIP = Path(__file__).parent.parent / "fixtures" / "synthetic_flash_clip.mp4"
FLASH_CLIP_META = Path(__file__).parent.parent / "fixtures" / "synthetic_flash_clip.meta.json"


def _solid_frame(color_bgr: tuple[int, int, int], size: int = 128) -> np.ndarray:
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    frame[:, :] = color_bgr
    return frame


def _textured_frame(size: int = 128, seed: int = 0) -> np.ndarray:
    # Farneback needs actual multi-pixel structure (edges/blobs) to lock
    # onto - pure per-pixel noise has no coherent local structure (each
    # polynomial-expansion neighborhood is uncorrelated garbage, so flow
    # estimates are near-random) and a smooth gradient is ambiguous in the
    # opposite direction (a shifted linear ramp looks like the unshifted
    # ramp at a nearby intensity - the classic aperture problem). Random
    # filled circles give Farneback well-defined edges to track.
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size), dtype=np.uint8)
    for _ in range(max(20, size // 5)):
        cx, cy = rng.integers(0, size, 2)
        radius = rng.integers(max(2, size // 20), max(3, size // 8))
        color = int(rng.integers(50, 255))
        cv2.circle(img, (int(cx), int(cy)), int(radius), color, -1)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def _shifted_frames(n: int, shift_per_frame: int, size: int = 128, seed: int = 0) -> list[np.ndarray]:
    base = _textured_frame(size, seed)
    return [np.roll(base, shift=shift_per_frame * i, axis=1) for i in range(n)]


# --- _check_whip_pan --------------------------------------------------------


def test_check_whip_pan_detects_consistent_both_side_motion() -> None:
    before = _shifted_frames(5, shift_per_frame=20, seed=1)
    after = _shifted_frames(5, shift_per_frame=20, seed=1)
    result = _check_whip_pan(before, after)
    assert result is not None
    direction, magnitude = result
    assert direction in ("left", "right", "up", "down")
    assert magnitude > 0


def test_check_whip_pan_rejects_one_sided_spike() -> None:
    # Strong motion before, none after - per spec sec 8.3, must NOT call whip_pan.
    before = _shifted_frames(5, shift_per_frame=20, seed=1)
    after = [_textured_frame(seed=2)] * 5  # static
    result = _check_whip_pan(before, after)
    assert result is None


def test_check_whip_pan_rejects_opposing_directions() -> None:
    before = _shifted_frames(5, shift_per_frame=20, seed=1)
    after = _shifted_frames(5, shift_per_frame=-20, seed=1)
    result = _check_whip_pan(before, after)
    assert result is None


# --- _check_zoom_discontinuity ----------------------------------------------


def test_check_zoom_discontinuity_none_when_insufficient_frames() -> None:
    assert _check_zoom_discontinuity([], []) is None
    assert _check_zoom_discontinuity([_textured_frame()], [_textured_frame()]) is None


# --- _check_dissolve ---------------------------------------------------------


def test_check_dissolve_true_for_sustained_elevated_distance() -> None:
    # 6 frames smoothly blending from red to blue - each adjacent pair has a
    # meaningfully elevated (but not single-spike) hist distance.
    steps = 6
    frames = []
    for i in range(steps):
        alpha = i / (steps - 1)
        color = (int(255 * (1 - alpha)), 0, int(255 * alpha))  # BGR: red -> blue
        frames.append(_solid_frame(color))
    assert _check_dissolve(frames) is True


def test_check_dissolve_false_for_single_spike() -> None:
    frames = [_solid_frame((0, 0, 255))] * 3 + [_solid_frame((255, 0, 0))] * 3
    # Only one adjacent pair differs (the cut) - not a sustained run.
    assert _check_dissolve(frames) is False


def test_hist_distance_zero_for_identical_frames() -> None:
    frame = _solid_frame((0, 255, 0))
    assert _hist_distance(frame, frame) == pytest.approx(0.0, abs=1e-6)


# --- end-to-end detect_cuts() -----------------------------------------------


def test_detect_cuts_classifies_hard_cuts_as_cut_on_synthetic_clip() -> None:
    if not SYNTHETIC_CLIP.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")
    transitions = detect_cuts(SYNTHETIC_CLIP, min_scene_len_frames=3)
    assert len(transitions) >= 2
    for transition in transitions:
        assert transition.type == TransitionType.cut
        assert transition.evidence is not None


def test_detect_cuts_classifies_flash_on_flash_clip() -> None:
    if not FLASH_CLIP.exists():
        pytest.skip("run tests/fixtures/make_flash_clip.py first")
    transitions = detect_cuts(FLASH_CLIP, min_scene_len_frames=3)
    assert len(transitions) >= 1
    # The degenerate-case guard from INSTRUCTIONS.md Unit 1.5: a classifier
    # that labels everything "cut" would still pass a naive test - assert
    # something ELSE shows up given a real non-cut transition exists.
    types = {t.type for t in transitions}
    assert types != {TransitionType.cut}, (
        f"expected at least one non-cut classification for a flash transition, got {types}"
    )
