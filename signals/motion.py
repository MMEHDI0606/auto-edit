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

from pathlib import Path

from schemas.models import MotionCurve


def estimate_affine_motion(frame_a, frame_b) -> tuple:
    """Returns (M, inlier_count) from ORB/SIFT + RANSAC partial affine.
    Pure function over two frames (numpy arrays) - keep it free of file I/O
    so it's directly unit-testable against synthetic frame pairs.
    """
    raise NotImplementedError


def dense_flow_fallback(frame_a, frame_b, *, method: str = "farneback"):
    """Farneback (default) or RAFT dense optical flow, used when
    estimate_affine_motion's inlier count falls below threshold."""
    raise NotImplementedError


def fit_motion_curve(tx_series: list[float], ty_series: list[float], scale_series: list[float]) -> MotionCurve:
    """Fits accumulated per-frame (tx, ty, scale) to the primitive+easing
    library; falls back to raw_keyframes when residual is too high.
    Also computes `shake_score` as the high-frequency energy of (tx, ty)
    after detrending - handheld/shake is reported as a ShotEffect
    (EffectType.shake), not as a MotionCurve field, since it coexists with
    an underlying primitive (e.g. punch_in + shake).
    """
    raise NotImplementedError


def compute_shake_score(tx_series: list[float], ty_series: list[float]) -> float:
    raise NotImplementedError


def extract_shot_motion(normalized_video_path: Path, t_in: float, t_out: float) -> MotionCurve:
    """Top-level entry point used by trace_builder.py - handles the
    frame-pair loop, affine/flow fallback, and curve fit for a single shot."""
    raise NotImplementedError
