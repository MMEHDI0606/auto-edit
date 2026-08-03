"""
Unit 1.6 done criteria: fit_motion_curve recovers a known punch_in from a
synthetic frame sequence with a KNOWN affine scale ramp, within tolerance.
Also covers estimate_affine_motion's fallback trigger, dense_flow_fallback,
and compute_shake_score's high-frequency detection - all against synthetic
data (no real video needed, per INSTRUCTIONS.md).
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from signals.motion import (
    compute_shake_score,
    dense_flow_fallback,
    estimate_affine_motion,
    fit_motion_curve,
)
from schemas.models import MotionPrimitive


def _textured_image(size: int = 240, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(size, size, 3), dtype=np.uint8)


def _zoom_frames(n: int, from_scale: float, to_scale: float) -> list[np.ndarray]:
    base = _textured_image()
    h, w = base.shape[:2]
    center = (w / 2, h / 2)
    frames = []
    for i in range(n):
        s = from_scale + (to_scale - from_scale) * i / (n - 1)
        M = cv2.getRotationMatrix2D(center, 0, s)
        frames.append(cv2.warpAffine(base, M, (w, h), borderMode=cv2.BORDER_REFLECT))
    return frames


def test_fit_motion_curve_recovers_known_punch_in() -> None:
    frames = _zoom_frames(10, from_scale=1.0, to_scale=1.1)

    tx_series, ty_series, scale_series = [0.0], [0.0], [1.0]
    cum_tx = cum_ty = 0.0
    cum_scale = 1.0
    for a, b in zip(frames[:-1], frames[1:]):
        M, inliers = estimate_affine_motion(a, b)
        assert M is not None and inliers >= 10  # textured image must yield good ORB matches
        tx = float(M[0, 2])
        ty = float(M[1, 2])
        scale = float(math.sqrt(M[0, 0] ** 2 + M[1, 0] ** 2))
        cum_tx += tx
        cum_ty += ty
        cum_scale *= scale
        tx_series.append(cum_tx)
        ty_series.append(cum_ty)
        scale_series.append(cum_scale)

    curve = fit_motion_curve(tx_series, ty_series, scale_series)
    assert curve.primitive == MotionPrimitive.punch_in
    assert abs(curve.to_scale - 1.1) < 0.03


def test_fit_motion_curve_recovers_static_for_no_motion() -> None:
    n = 8
    curve = fit_motion_curve([0.0] * n, [0.0] * n, [1.0] * n)
    assert curve.primitive == MotionPrimitive.static


def test_estimate_affine_motion_returns_none_for_textureless_frames() -> None:
    blank_a = np.full((100, 100, 3), 128, dtype=np.uint8)
    blank_b = np.full((100, 100, 3), 128, dtype=np.uint8)
    M, inliers = estimate_affine_motion(blank_a, blank_b)
    assert M is None
    assert inliers == 0


def test_dense_flow_fallback_recovers_translation_direction() -> None:
    base = _textured_image(size=128, seed=2)
    shifted = np.roll(base, shift=5, axis=1)  # shift content rightward
    tx, ty, scale = dense_flow_fallback(base, shifted)
    # Farneback flow measures displacement FROM frame_a TO frame_b - content
    # moved right, so the flow field should show a positive x-component.
    assert tx > 0


def test_compute_shake_score_detects_high_frequency_oscillation() -> None:
    fps = 30
    n = 60
    t = np.arange(n) / fps
    # 8Hz oscillation riding on a slow linear pan - shake score should catch
    # the oscillation after detrending the pan away.
    tx_series = (2.0 * t + 3.0 * np.sin(2 * np.pi * 8 * t)).tolist()
    ty_series = [0.0] * n

    amplitude_px, freq_hz = compute_shake_score(tx_series, ty_series, fps=fps)
    assert amplitude_px > 1.0
    assert abs(freq_hz - 8.0) <= 2.0  # FFT bin resolution tolerance


def test_compute_shake_score_near_zero_for_smooth_pan() -> None:
    fps = 30
    n = 60
    t = np.arange(n) / fps
    tx_series = (2.0 * t).tolist()  # pure linear pan, no shake
    ty_series = [0.0] * n

    amplitude_px, _freq_hz = compute_shake_score(tx_series, ty_series, fps=fps)
    assert amplitude_px < 0.5
