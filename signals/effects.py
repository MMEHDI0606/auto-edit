"""
L1 - per-shot effect detection: freeze, speed ramp, RGB split/glitch,
flash/strobe, blur pulse, vignette/grade stats, overlay/grain, masks.
See RECUT_SPEC.md sec 3.5.

Each detector below returns None when the effect is absent - trace_builder
only appends non-None results to Shot.effects. This is what makes L2's
evidence gate meaningful: if this module didn't flag glitch on a shot, the
enum of legal L2 labels for that shot excludes "glitch" (see
semantics/gating.py) - do not add a detector that "sort of always fires
weakly"; low-magnitude effects should return None below a tuned threshold
rather than a low-confidence positive.

Grade note (resolves spec open question #3): grade_stats() below computes
DESCRIPTIVE statistics only (contrast/saturation/temp). It must not
synthesize or return a 3D LUT in v1 - Grade.lut_available stays False until
that decision is deliberately revisited (see schemas/models.py::Grade and
DESIGN_NOTES.md).

Masks/cutouts (SAM2/rembg) are OPTIONAL and gated behind a feature flag -
see DESIGN_NOTES.md "Scope trim": do not block Phase 1 on this detector.
"""

from __future__ import annotations

import cv2
import numpy as np

from schemas.models import EffectType, Grade, ShotEffect

# Unit 1.3 tunables - see module docstring / INSTRUCTIONS.md Unit 1.3.
WATERMARK_CORNER_FRACTION = 0.15  # outer 15% width/height in each corner
WATERMARK_VARIANCE_THRESHOLD = 12.0  # near-zero temporal variance (0-255 scale) => static region
WATERMARK_MIN_LUMINANCE = 20.0  # excludes plain black letterbox bars from candidates

PARAM_SCHEMAS: dict[str, dict] = {
    # Per-effect-type parameter shape documentation for ShotEffect.params.
    # Keep this in sync as detectors are implemented; validate params against
    # it before constructing a ShotEffect so malformed params fail at
    # extraction time, not at render time.
    "freeze": {"required": ["duration_f"]},
    "speed_ramp": {"required": ["segments"]},  # list of {t_in, t_out, rate}
    "rgb_split": {"required": ["offset_px_r", "offset_px_b"]},
    "flash": {"required": ["t", "duration_f"]},
    "blur_pulse": {"required": ["t_in", "t_out", "laplacian_dip"]},
    "shake": {"required": ["amplitude_px", "freq_hz"]},
    "overlay_grain": {"required": ["intensity"]},
    "mask_cutout": {"required": ["mask_ref"]},
}


FREEZE_DIFF_THRESHOLD = 1.0  # mean cv2.absdiff, 0-255 scale
FREEZE_MIN_RUN_FRAMES = 6  # ~0.2s at 30fps


def detect_freeze(shot_frames: list[np.ndarray], audio_active: bool) -> ShotEffect | None:
    """frame diff ~ 0 while audio continues.

    `audio_active` reflects the WHOLE shot (per the stub's own signature) -
    a freeze with silence throughout isn't a freeze-frame effect, it's just
    a static shot, per spec sec 3.5's detection signal ("frame diff ~ 0
    WHILE audio continues")."""
    if not audio_active or len(shot_frames) < FREEZE_MIN_RUN_FRAMES + 1:
        return None

    diffs = [float(np.mean(cv2.absdiff(a, b))) for a, b in zip(shot_frames[:-1], shot_frames[1:])]

    best_len, best_start = 0, None
    run_len, run_start = 0, None
    for i, d in enumerate(diffs):
        if d < FREEZE_DIFF_THRESHOLD:
            if run_start is None:
                run_start = i
            run_len += 1
            if run_len > best_len:
                best_len, best_start = run_len, run_start
        else:
            run_start, run_len = None, 0

    if best_len < FREEZE_MIN_RUN_FRAMES:
        return None

    return ShotEffect(type=EffectType.freeze, params={"duration_f": best_len + 1}, confidence=1.0)


def detect_speed_ramp(motion_magnitude_series, audio_pitch_series) -> ShotEffect | None:
    """Motion magnitude discontinuity within a shot + audio pitch/tempo
    shift. Approximate with 2-3 linear segments (spec sec 8.3: information
    is genuinely destroyed by a speed ramp; do not attempt full curve
    recovery) and flag low confidence."""
    raise NotImplementedError


def detect_rgb_split(shot_frames) -> ShotEffect | None:
    """Per-channel cross-correlation offset > 0."""
    raise NotImplementedError


FLASH_SIGMA_THRESHOLD = 2.0
FLASH_BEAT_TOLERANCE_S = 0.1


def detect_flash(luminance_series: list[tuple[float, float]], beat_grid_s: list[float]) -> ShotEffect | None:
    """Luminance spikes at beat positions.

    `luminance_series` is [(t, mean_luminance), ...] - the stub's bare
    `luminance_series` name didn't specify a shape and a per-frame
    timestamp is required to check beat-proximity, so this is (t, value)
    pairs, not a plain value list. No caller existed yet to break.

    NOTE: this is a distinct, shot-INTERNAL flash detector from
    signals/cuts.py's transition-boundary flash check (Unit 1.5) - that
    one classifies a *cut type*, this one flags a *mid-shot effect*. The
    luminance-spike math is similar by coincidence, not shared code, per
    the module docstring's instruction to keep them separate.
    """
    if len(luminance_series) < 3 or not beat_grid_s:
        return None

    times = [t for t, _ in luminance_series]
    values = np.array([v for _, v in luminance_series], dtype=np.float64)
    mean_lum, std_lum = float(np.mean(values)), float(np.std(values)) + 1e-6

    best: tuple[float, float] | None = None  # (t, sigma)
    for t, value in zip(times, values):
        sigma = (value - mean_lum) / std_lum
        if sigma <= FLASH_SIGMA_THRESHOLD:
            continue
        if not any(abs(t - beat) <= FLASH_BEAT_TOLERANCE_S for beat in beat_grid_s):
            continue
        if best is None or sigma > best[1]:
            best = (t, sigma)

    if best is None:
        return None

    t, sigma = best
    return ShotEffect(
        type=EffectType.flash, params={"t": t, "duration_f": 1}, confidence=min(1.0, sigma / 4)
    )


BLUR_DIP_FRACTION = 0.4  # dip below this fraction of the shot's median Laplacian variance


def detect_blur_pulse(shot_frames: list[np.ndarray], *, fps: int = 30) -> ShotEffect | None:
    """Laplacian variance dips.

    Signature extended with `fps` (default matching Settings.normalize_fps)
    - t_in/t_out need real time units and shot_frames alone carries no
      timing; no caller existed yet to break.
    """
    if len(shot_frames) < 3:
        return None

    variances = []
    for frame in shot_frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        variances.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))

    median_var = float(np.median(variances))
    if median_var <= 1e-6:
        return None
    threshold = median_var * BLUR_DIP_FRACTION

    dip_indices = [i for i, v in enumerate(variances) if v < threshold]
    if not dip_indices:
        return None

    runs: list[tuple[int, int]] = []
    start = prev = dip_indices[0]
    for idx in dip_indices[1:]:
        if idx == prev + 1:
            prev = idx
        else:
            runs.append((start, prev))
            start = prev = idx
    runs.append((start, prev))

    best_start, best_end = max(runs, key=lambda r: r[1] - r[0])
    dip_min_var = min(variances[best_start : best_end + 1])
    laplacian_dip = 1.0 - (dip_min_var / median_var)

    return ShotEffect(
        type=EffectType.blur_pulse,
        params={"t_in": best_start / fps, "t_out": (best_end + 1) / fps, "laplacian_dip": laplacian_dip},
        confidence=1.0,
    )


def grade_stats(shot_frames) -> Grade:
    """Per-shot histogram stats vs a neutral reference. Descriptive only -
    see module docstring. Must return Grade(lut_available=False)."""
    raise NotImplementedError


def detect_mask_cutout(shot_frames, *, enabled: bool) -> ShotEffect | None:
    """SAM2/rembg subject isolation. `enabled` defaults to False at the
    call site until Phase 3+ - see DESIGN_NOTES.md "Scope trim"."""
    if not enabled:
        return None
    raise NotImplementedError


def _corner_boxes(h: int, w: int, fraction: float) -> dict[str, tuple[int, int, int, int]]:
    cw, ch = max(1, int(w * fraction)), max(1, int(h * fraction))
    return {
        "top_left": (0, 0, cw, ch),
        "top_right": (w - cw, 0, cw, ch),
        "bottom_left": (0, h - ch, cw, ch),
        "bottom_right": (w - cw, h - ch, cw, ch),
    }


def _median_blur_safe(patch: np.ndarray) -> np.ndarray:
    """cv2.medianBlur needs an odd kernel size smaller than both patch
    dimensions - clamp down for small corner patches rather than raising."""
    ksize = min(15, patch.shape[0], patch.shape[1])
    if ksize % 2 == 0:
        ksize -= 1
    if ksize < 3:
        return patch
    return cv2.medianBlur(patch, ksize)


def mask_watermark_regions(
    shot_frames: list[np.ndarray],
) -> tuple[list[np.ndarray], list[tuple[int, int, int, int]]]:
    """Detect+mask static corner regions (TikTok/IG watermark bugs) BEFORE
    OCR/flow run on a shot - spec sec 8.3 mitigation for watermark
    pollution. Must be called upstream by trace_builder before text.py and
    motion.py see the frames, not treated as a separate optional pass.

    Static-corner masking only - this is a preprocessing step, not a full
    watermark detector. Moving/rotating/per-platform-specific watermark
    recognition is out of scope.

    Returns (masked_frames, masked_rects_px) where masked_rects_px is
    [(x, y, w, h), ...] in pixel coordinates - trace_builder logs these into
    EvidenceMeta.
    """
    if not shot_frames:
        return [], []

    # Sample every 10th frame across the whole shot to build the variance
    # map - per-frame would be wasteful and isn't needed for a per-shot,
    # temporally-static signal.
    sample = shot_frames[::10] if len(shot_frames) > 10 else shot_frames
    stacked = np.stack([f.astype(np.float32) for f in sample], axis=0)

    variance_map = np.var(stacked, axis=0)
    mean_map = stacked.mean(axis=0)
    if variance_map.ndim == 3:
        variance_map = variance_map.mean(axis=2)
        mean_map = mean_map.mean(axis=2)

    h, w = variance_map.shape
    masked_rects: list[tuple[int, int, int, int]] = []
    for x, y, cw, ch in _corner_boxes(h, w, WATERMARK_CORNER_FRACTION).values():
        region_var = variance_map[y : y + ch, x : x + cw]
        region_lum = mean_map[y : y + ch, x : x + cw]
        # Near-zero temporal variance = content never changes here (a static
        # logo bug); non-trivial mean luminance excludes plain black bars,
        # which are also static but not a watermark worth masking.
        if region_var.mean() < WATERMARK_VARIANCE_THRESHOLD and region_lum.mean() > WATERMARK_MIN_LUMINANCE:
            masked_rects.append((x, y, cw, ch))

    if not masked_rects:
        return list(shot_frames), []

    masked_frames = []
    for frame in shot_frames:
        out = frame.copy()
        for x, y, cw, ch in masked_rects:
            out[y : y + ch, x : x + cw] = _median_blur_safe(out[y : y + ch, x : x + cw])
        masked_frames.append(out)

    return masked_frames, masked_rects
