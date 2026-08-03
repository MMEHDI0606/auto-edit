"""
The 1:1 mapping between L1-detected primitives and renderable effects. See
RECUT_SPEC.md sec 7.2. This file is the CONTRACT (parameter names + types
each primitive expects) - every RenderEngine implementation must honor it,
whether it executes the primitive in Python, in a Remotion component, or
in a Revideo scene.

PRIMITIVES: punch_in, slow_push, whip_pan, shake, flash, rgb_split, freeze,
speed_ramp, text_pop, text_typewriter, text_word_by_word, caption_karaoke.

Rule (spec sec 7.2): if L1 detects something with no library primitive
here, the engine must degrade gracefully to the nearest match AND flag it
in the render report - never silently drop the effect and never crash.
"""

from __future__ import annotations

PRIMITIVE_PARAM_CONTRACTS: dict[str, dict] = {
    "punch_in": {"from_scale": float, "to_scale": float, "easing": str},
    "slow_push": {"from_scale": float, "to_scale": float, "easing": str},
    "whip_pan": {"direction": str, "duration_f": int},
    "shake": {"amplitude_px": float, "freq_hz": float},
    "flash": {"t": float, "duration_f": int},
    "rgb_split": {"offset_px_r": float, "offset_px_b": float},
    "freeze": {"duration_f": int},
    "speed_ramp": {"segments": list},
    "text_pop": {"in_duration_f": int},
    "text_typewriter": {"chars_per_f": float},
    "text_word_by_word": {"words_per_f": float},
    "caption_karaoke": {"transcript_words": list},
}


def nearest_fallback_primitive(unknown_primitive_name: str) -> str:
    """Returns the closest supported primitive name for something L1
    flagged that has no exact library match. Must always return SOMETHING
    (never None/raise) - the caller is responsible for logging the
    degradation into RenderReport.approximations."""
    raise NotImplementedError
