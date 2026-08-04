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



# Maps every schemas.models.MotionPrimitive value to the nearest name that
# actually appears as a key in PRIMITIVE_PARAM_CONTRACTS above. Deviates
# from the literal example in INSTRUCTIONS.md Unit 2.6 ("whip_pan -> pan")
# because that example doesn't match this scaffold's real data: whip_pan
# IS already a full contract above, and there is no standalone "pan"
# entry - so the sensible fallback direction is the other way (pan -> the
# nearest thing that exists, whip_pan), not what the example literally
# said. Primitives that are already supported (or need no substitution at
# all) map to themselves so every MotionPrimitive value has SOME entry:
#   - static: no motion primitive needed at all - caller renders a plain
#     static frame for the duration, this isn't really a "fallback."
#   - keyframed: the renderer applies MotionCurve.raw_keyframes directly;
#     there's no primitive to substitute, the raw curve IS the render.
_FALLBACK_TABLE: dict[str, str] = {
    "punch_in": "punch_in",
    "slow_push": "slow_push",
    "zoom_out_reveal": "punch_in",  # inverse direction, closest available scale-ramp primitive
    "pan": "whip_pan",  # no standalone "pan" render primitive exists - whip_pan is the closest translation-based one
    "whip": "whip_pan",  # exact semantic match (whip_pan IS what "whip" renders as)
    "static": "static",
    "keyframed": "keyframed",
}
_DEFAULT_FALLBACK = "static"  # safest universal fallback for a name outside MotionPrimitive entirely


def nearest_fallback_primitive(unknown_primitive_name: str) -> str:
    """Returns the closest supported primitive name for something L1
    flagged that has no exact library match. Must always return SOMETHING
    (never None/raise) - the caller is responsible for logging the
    degradation into RenderReport.approximations."""
    return _FALLBACK_TABLE.get(unknown_primitive_name, _DEFAULT_FALLBACK)
