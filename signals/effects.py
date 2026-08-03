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

from schemas.models import Grade, ShotEffect

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


def detect_freeze(shot_frames, audio_active: bool) -> ShotEffect | None:
    """frame diff ~ 0 while audio continues."""
    raise NotImplementedError


def detect_speed_ramp(motion_magnitude_series, audio_pitch_series) -> ShotEffect | None:
    """Motion magnitude discontinuity within a shot + audio pitch/tempo
    shift. Approximate with 2-3 linear segments (spec sec 8.3: information
    is genuinely destroyed by a speed ramp; do not attempt full curve
    recovery) and flag low confidence."""
    raise NotImplementedError


def detect_rgb_split(shot_frames) -> ShotEffect | None:
    """Per-channel cross-correlation offset > 0."""
    raise NotImplementedError


def detect_flash(luminance_series, beat_grid_s: list[float]) -> ShotEffect | None:
    """Luminance spikes at beat positions."""
    raise NotImplementedError


def detect_blur_pulse(shot_frames) -> ShotEffect | None:
    """Laplacian variance dips."""
    raise NotImplementedError


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


def mask_watermark_regions(shot_frames, *, static_corner_regions: list[tuple]) -> list:
    """Detect+mask static corner regions (TikTok/IG watermark bugs) BEFORE
    OCR/flow run on a shot - spec sec 8.3 mitigation for watermark
    pollution. Must be called upstream by trace_builder before text.py and
    motion.py see the frames, not treated as a separate optional pass.
    """
    raise NotImplementedError
