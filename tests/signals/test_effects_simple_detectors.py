"""
Unit 1.13 done criteria: detect_freeze/detect_flash/detect_blur_pulse each
fire on a hand-constructed positive example and do NOT fire on 2-3
negative examples (false-positive spot check, not just true-positive) -
all against synthetic frame arrays.
"""

from __future__ import annotations

import cv2
import numpy as np

from signals.effects import detect_blur_pulse, detect_flash, detect_freeze


def _textured_frame(size: int = 64, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size), dtype=np.uint8)
    for _ in range(30):
        cx, cy = rng.integers(0, size, 2)
        r = rng.integers(3, 10)
        color = int(rng.integers(50, 255))
        cv2.circle(img, (int(cx), int(cy)), int(r), color, -1)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def _varying_frames(n: int) -> list[np.ndarray]:
    return [_textured_frame(seed=i) for i in range(n)]


# --- detect_freeze -----------------------------------------------------------


def test_detect_freeze_fires_on_identical_frame_run_with_audio() -> None:
    frozen_frame = _textured_frame(seed=1)
    frames = _varying_frames(3) + [frozen_frame] * 8 + _varying_frames(3)
    effect = detect_freeze(frames, audio_active=True)
    assert effect is not None
    assert effect.type.value == "freeze"
    assert effect.params["duration_f"] >= 6


def test_detect_freeze_none_without_audio() -> None:
    frozen_frame = _textured_frame(seed=1)
    frames = _varying_frames(3) + [frozen_frame] * 8 + _varying_frames(3)
    assert detect_freeze(frames, audio_active=False) is None


def test_detect_freeze_none_when_frames_keep_changing() -> None:
    frames = _varying_frames(15)
    assert detect_freeze(frames, audio_active=True) is None


# --- detect_flash --------------------------------------------------------------


def test_detect_flash_fires_at_beat_position() -> None:
    beat_grid = [0.5]
    # baseline luminance ~50 with small noise, one spike to 200 exactly at t=0.5
    series = [(round(i * 0.05, 3), 50.0 + (i % 2)) for i in range(20)]
    series[10] = (0.5, 200.0)
    effect = detect_flash(series, beat_grid)
    assert effect is not None
    assert effect.type.value == "flash"
    assert effect.params["t"] == 0.5


def test_detect_flash_none_when_spike_not_near_beat() -> None:
    beat_grid = [0.5]
    series = [(round(i * 0.05, 3), 50.0 + (i % 2)) for i in range(20)]
    series[3] = (0.15, 200.0)  # far from the only beat at 0.5
    assert detect_flash(series, beat_grid) is None


def test_detect_flash_none_without_spike() -> None:
    beat_grid = [0.5]
    series = [(round(i * 0.05, 3), 50.0 + (i % 2)) for i in range(20)]
    assert detect_flash(series, beat_grid) is None


# --- detect_blur_pulse ---------------------------------------------------------


def test_detect_blur_pulse_fires_on_middle_blur_dip() -> None:
    sharp = [_textured_frame(seed=i) for i in range(4)]
    blurred = [cv2.GaussianBlur(_textured_frame(seed=i + 100), (15, 15), 0) for i in range(4)]
    frames = sharp + blurred + sharp
    effect = detect_blur_pulse(frames, fps=30)
    assert effect is not None
    assert effect.type.value == "blur_pulse"
    assert effect.params["t_in"] < effect.params["t_out"]
    assert effect.params["laplacian_dip"] > 0


def test_detect_blur_pulse_none_when_uniformly_sharp() -> None:
    frames = [_textured_frame(seed=i) for i in range(10)]
    assert detect_blur_pulse(frames, fps=30) is None
