"""
Unit 1.15 done criteria: detect_rgb_split() fires on a constructed
chromatic-aberration/glitch example with a plausible offset, and does NOT
fire on normal shots - including a real h264-compressed shot (checking the
noise-floor threshold is high enough to exclude compression artifacts,
per spec sec 8.3's "compression artifacts" failure mode).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from signals.effects import detect_rgb_split

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


def _textured_frame(size: int = 128, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size), dtype=np.uint8)
    for _ in range(40):
        cx, cy = rng.integers(0, size, 2)
        r = rng.integers(3, 12)
        color = int(rng.integers(50, 255))
        cv2.circle(img, (int(cx), int(cy)), int(r), color, -1)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def _shift_channel(frame: np.ndarray, channel: int, shift_px: int) -> np.ndarray:
    out = frame.copy()
    out[:, :, channel] = np.roll(frame[:, :, channel], shift_px, axis=1)
    return out


def test_fires_on_constructed_rgb_split() -> None:
    frames = [_shift_channel(_textured_frame(seed=i), channel=2, shift_px=4) for i in range(5)]  # shift R channel
    effect = detect_rgb_split(frames)
    assert effect is not None
    assert effect.type.value == "rgb_split"
    assert effect.params["offset_px_r"] > 1.0
    # Plausible magnitude - phase correlation on a 4px roll should land
    # somewhere in a sane neighborhood, not an arbitrary huge number.
    assert 1.5 < effect.params["offset_px_r"] < 20.0


def test_none_on_normal_synthetic_frames() -> None:
    frames = [_textured_frame(seed=i) for i in range(5)]
    assert detect_rgb_split(frames) is None


def test_none_on_real_compressed_shot() -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")
    cap = cv2.VideoCapture(str(FIXTURE))
    frames = []
    for _ in range(15):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    assert len(frames) > 0
    # A normal h264-compressed shot (no real glitch) must not false-positive
    # on channel-alignment noise introduced by compression.
    assert detect_rgb_split(frames) is None


def test_none_on_empty_input() -> None:
    assert detect_rgb_split([]) is None
