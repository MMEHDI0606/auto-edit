"""
L1 - camera / framing motion estimation. See RECUT_SPEC.md sec 3.2.

Per-shot pipeline:
  1. ORB/SIFT feature match + cv2.estimateAffinePartial2D(RANSAC) per frame pair.
  2. If inlier count < Settings.flow_inlier_fallback_threshold, fall back to
     dense flow (Farneback; RAFT optional if GPU budget exists) - THIS
     THRESHOLD AND FALLBACK RULE IS NOT OPTIONAL, it is what the spec left
     underspecified as "fallback when feature matching fails on low-texture
     frames" - common.config carries the concrete number, this module must
     honor it and record which method was actually used per shot (goes into
     EvidenceMeta.model_versions / a per-shot evidence field).
  3. Accumulate (tx, ty, scale, rotation) into per-shot curves.
  4. Fit each curve to the small primitive+easing library
     (schemas.models.MotionPrimitive / Easing). If residual exceeds the fit
     threshold, store raw keyframes instead of forcing a bad-fit primitive
     (schemas.models.MotionCurve.raw_keyframes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from common.config import load_settings
from schemas.models import Easing, MotionCurve, MotionPrimitive

FIT_RESIDUAL_THRESHOLD = 0.05
SHAKE_HIGH_PASS_HZ = 4.0  # handheld shake is typically 5-15Hz at ~30fps
WHIP_DISPLACEMENT_PX_THRESHOLD = 150.0  # cumulative pan displacement above this reads as "whip" not "pan"


def estimate_affine_motion(frame_a, frame_b) -> tuple:
    """Returns (M, inlier_count) from ORB + RANSAC partial affine.
    Pure function over two frames (numpy arrays) - keep it free of file I/O
    so it's directly unit-testable against synthetic frame pairs.
    Returns (None, 0) when fewer than 10 good matches are found - callers
    must fall back to dense_flow_fallback in that case.
    """
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY) if frame_a.ndim == 3 else frame_a
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY) if frame_b.ndim == 3 else frame_b

    orb = cv2.ORB_create(nfeatures=2000)
    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)

    if des_a is None or des_b is None or len(kp_a) < 2 or len(kp_b) < 2:
        return None, 0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn_matches = matcher.knnMatch(des_a, des_b, k=2)

    good = []
    for pair in knn_matches:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:  # Lowe's ratio test
            good.append(m)

    if len(good) < 10:
        return None, 0

    pts_a = np.float32([kp_a[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    pts_b = np.float32([kp_b[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    M, inliers = cv2.estimateAffinePartial2D(pts_a, pts_b, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None:
        return None, 0
    inlier_count = int(inliers.sum()) if inliers is not None else 0
    return M, inlier_count


def dense_flow_fallback(frame_a, frame_b, *, method: str = "farneback") -> tuple[float, float, float]:
    """Farneback dense optical flow, used when estimate_affine_motion's
    inlier count falls below threshold. Returns an approximate (tx, ty, scale)
    for this frame pair: tx/ty from the median flow vector, scale from the
    mean radial flow component relative to the frame diagonal."""
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY) if frame_a.ndim == 3 else frame_a
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY) if frame_b.ndim == 3 else frame_b

    flow = cv2.calcOpticalFlowFarneback(
        gray_a, gray_b, None, pyr_scale=0.5, levels=3, winsize=15, iterations=3,
        poly_n=5, poly_sigma=1.2, flags=0,
    )

    tx = float(np.median(flow[..., 0]))
    ty = float(np.median(flow[..., 1]))

    h, w = gray_a.shape
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = xx - cx, yy - cy
    dist = np.sqrt(dx**2 + dy**2) + 1e-6
    radial_component = (flow[..., 0] * dx + flow[..., 1] * dy) / dist
    diagonal = math.hypot(h, w)
    scale = 1.0 + float(np.mean(radial_component)) / diagonal

    return tx, ty, scale


def _decompose_affine(M: np.ndarray) -> tuple[float, float, float, float]:
    tx = float(M[0, 2])
    ty = float(M[1, 2])
    scale = float(math.sqrt(M[0, 0] ** 2 + M[1, 0] ** 2))
    rotation = float(math.atan2(M[1, 0], M[0, 0]))
    return tx, ty, scale, rotation


_EASING_FUNCS: dict[Easing, Callable[[np.ndarray], np.ndarray]] = {
    Easing.linear: lambda t: t,
    Easing.ease_in: lambda t: t**2,
    Easing.ease_out: lambda t: 1 - (1 - t) ** 2,
    Easing.ease_in_out: lambda t: t * t * (3 - 2 * t),  # cubic smoothstep
    Easing.spring: lambda t: 1 - np.exp(-6 * t) * np.cos(4 * np.pi * t),  # damped-oscillation approximation
}


def _residual(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Sum of squared error normalized by series length, per INSTRUCTIONS.md
    Unit 1.6 - callers compare residuals only within a fit search, this is
    not intended as a cross-unit-normalized error metric."""
    if len(actual) == 0:
        return 0.0
    return float(np.sum((actual - predicted) ** 2)) / len(actual)


def _best_easing_fit(actual: np.ndarray, from_v: float, to_v: float) -> tuple[Easing, float]:
    n = len(actual)
    t = np.linspace(0.0, 1.0, n) if n > 1 else np.array([0.0])
    best_easing, best_residual = Easing.linear, float("inf")
    for easing, fn in _EASING_FUNCS.items():
        predicted = from_v + (to_v - from_v) * fn(t)
        r = _residual(actual, predicted)
        if r < best_residual:
            best_easing, best_residual = easing, r
    return best_easing, best_residual


def fit_motion_curve(tx_series: list[float], ty_series: list[float], scale_series: list[float]) -> MotionCurve:
    """Fits accumulated per-frame (tx, ty, scale) to the primitive+easing
    library; falls back to raw_keyframes when residual is too high.
    """
    tx = np.asarray(tx_series, dtype=np.float64)
    ty = np.asarray(ty_series, dtype=np.float64)
    scale = np.asarray(scale_series, dtype=np.float64) if len(scale_series) else np.ones_like(tx)

    candidates: list[tuple[MotionPrimitive, Easing, float, dict]] = []

    # static: near-zero everywhere
    static_residual = (
        _residual(scale, np.full_like(scale, 1.0))
        + _residual(tx, np.zeros_like(tx))
        + _residual(ty, np.zeros_like(ty))
    )
    candidates.append(
        (MotionPrimitive.static, Easing.linear, static_residual,
         {"from_scale": 1.0, "to_scale": 1.0, "pan_tx": 0.0, "pan_ty": 0.0})
    )

    # scale-ramp primitives: punch_in / slow_push / zoom_out_reveal
    if len(scale) >= 2:
        from_scale, to_scale = float(scale[0]), float(scale[-1])
        easing, residual = _best_easing_fit(scale, from_scale, to_scale)
        if to_scale > from_scale:
            primitive = MotionPrimitive.punch_in if (to_scale - from_scale) > 0.05 else MotionPrimitive.slow_push
        else:
            primitive = MotionPrimitive.zoom_out_reveal
        candidates.append(
            (primitive, easing, residual,
             {"from_scale": from_scale, "to_scale": to_scale, "pan_tx": 0.0, "pan_ty": 0.0})
        )

    # translation-ramp primitives: pan / whip
    if len(tx) >= 2:
        from_tx, to_tx = float(tx[0]), float(tx[-1])
        from_ty, to_ty = float(ty[0]), float(ty[-1])
        easing_x, residual_x = _best_easing_fit(tx, from_tx, to_tx)
        easing_y, residual_y = _best_easing_fit(ty, from_ty, to_ty)
        # Use whichever axis carries more displacement to pick the
        # representative easing/residual - a shot's pan is rarely an equal
        # diagonal ramp on both axes.
        if abs(to_tx - from_tx) >= abs(to_ty - from_ty):
            easing, residual = easing_x, residual_x
        else:
            easing, residual = easing_y, residual_y
        displacement = math.hypot(to_tx - from_tx, to_ty - from_ty)
        primitive = MotionPrimitive.whip if displacement > WHIP_DISPLACEMENT_PX_THRESHOLD else MotionPrimitive.pan
        candidates.append(
            (primitive, easing, residual,
             {"from_scale": 1.0, "to_scale": 1.0, "pan_tx": to_tx - from_tx, "pan_ty": to_ty - from_ty})
        )

    best_primitive, best_easing, best_residual, best_params = min(candidates, key=lambda c: c[2])

    if best_residual > FIT_RESIDUAL_THRESHOLD:
        n = max(len(tx), len(ty), len(scale))
        raw_keyframes = [
            {
                "t": i,
                "tx": float(tx[i]) if i < len(tx) else 0.0,
                "ty": float(ty[i]) if i < len(ty) else 0.0,
                "scale": float(scale[i]) if i < len(scale) else 1.0,
            }
            for i in range(n)
        ]
        return MotionCurve(primitive=MotionPrimitive.keyframed, residual=best_residual, raw_keyframes=raw_keyframes)

    return MotionCurve(
        primitive=best_primitive,
        from_scale=best_params["from_scale"],
        to_scale=best_params["to_scale"],
        pan_tx=best_params["pan_tx"],
        pan_ty=best_params["pan_ty"],
        easing=best_easing,
        residual=best_residual,
    )


def compute_shake_score(tx_series: list[float], ty_series: list[float], *, fps: int = 30) -> tuple[float, float]:
    """Detrends (tx, ty) with a linear fit, then computes high-frequency
    (>=4Hz) energy via FFT. Returns (amplitude_px, freq_hz) - the two fields
    ShotEffect(type=EffectType.shake) needs (see signals/effects.py
    PARAM_SCHEMAS); this coexists with an underlying MotionCurve primitive,
    it is not itself a MotionCurve field.

    NOTE: signature extended with `fps` (stub omitted it) - converting FFT
    bin index to Hz is not possible without a sample rate, and nothing
    called this function yet to depend on the two-argument shape.
    """
    tx = np.asarray(tx_series, dtype=np.float64)
    ty = np.asarray(ty_series, dtype=np.float64)
    n = len(tx)
    if n < 4:
        return 0.0, 0.0

    t = np.arange(n)
    tx_detrended = tx - np.polyval(np.polyfit(t, tx, 1), t)
    ty_detrended = ty - np.polyval(np.polyfit(t, ty, 1), t)

    amplitude_px = float(np.sqrt(np.mean(tx_detrended**2 + ty_detrended**2)))

    # Sum the per-axis power spectra (not FFT of sqrt(tx^2+ty^2) - taking a
    # magnitude/abs before the FFT rectifies the signal and DOUBLES the
    # apparent frequency, e.g. an 8Hz oscillation on one axis reads as 16Hz).
    freqs = np.fft.rfftfreq(n, d=1.0 / fps)
    power = np.abs(np.fft.rfft(tx_detrended)) ** 2 + np.abs(np.fft.rfft(ty_detrended)) ** 2

    high_pass = freqs >= SHAKE_HIGH_PASS_HZ
    if not np.any(high_pass) or power[high_pass].sum() == 0:
        return amplitude_px, 0.0

    # argmax over the full array but zeroing out the low-frequency band first,
    # so the "dominant frequency in the high-pass band" is picked correctly.
    masked_power = np.where(high_pass, power, 0.0)
    dominant_idx = int(np.argmax(masked_power))
    return amplitude_px, float(freqs[dominant_idx])


@dataclass
class ShotMotionResult:
    """Return type for extract_shot_motion() - extended beyond a bare
    MotionCurve (the stub's declared type) to also carry the shake
    amplitude/frequency, since trace_builder needs both and re-deriving the
    tx/ty series a second time to get shake would mean decoding every shot's
    frames twice. No caller existed yet to break by widening this."""

    curve: MotionCurve
    shake_amplitude_px: float
    shake_freq_hz: float


def _read_shot_frames(video_path: Path, t_in: float, t_out: float) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_frame = int(round(t_in * fps))
    end_frame = int(round(t_out * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frames = []
    for _ in range(max(0, end_frame - start_frame)):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def extract_shot_motion(normalized_video_path: Path, t_in: float, t_out: float) -> ShotMotionResult:
    """Top-level entry point used by trace_builder.py - handles the
    frame-pair loop, affine/flow fallback, and curve fit for a single shot."""
    frames = _read_shot_frames(normalized_video_path, t_in, t_out)
    if len(frames) < 2:
        return ShotMotionResult(
            curve=MotionCurve(primitive=MotionPrimitive.static, residual=0.0),
            shake_amplitude_px=0.0,
            shake_freq_hz=0.0,
        )

    cap = cv2.VideoCapture(str(normalized_video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()

    fallback_threshold = load_settings().flow_inlier_fallback_threshold

    tx_series = [0.0]
    ty_series = [0.0]
    scale_series = [1.0]
    cum_tx = cum_ty = 0.0
    cum_scale = 1.0

    for frame_a, frame_b in zip(frames[:-1], frames[1:]):
        M, inlier_count = estimate_affine_motion(frame_a, frame_b)
        if M is not None and inlier_count >= fallback_threshold:
            tx, ty, scale, _rotation = _decompose_affine(M)
        else:
            tx, ty, scale = dense_flow_fallback(frame_a, frame_b)
        cum_tx += tx
        cum_ty += ty
        cum_scale *= scale
        tx_series.append(cum_tx)
        ty_series.append(cum_ty)
        scale_series.append(cum_scale)

    curve = fit_motion_curve(tx_series, ty_series, scale_series)
    amplitude_px, freq_hz = compute_shake_score(tx_series, ty_series, fps=int(round(fps)))

    return ShotMotionResult(curve=curve, shake_amplitude_px=amplitude_px, shake_freq_hz=freq_hz)
