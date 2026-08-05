"""
L3 orchestrator - Trace (+ optional SemanticAnnotations) -> Template.
See RECUT_SPEC.md sec 5.

This is the only compiler/ entry point other packages should import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from compiler.beat_snap import snap_duration_to_beat
from compiler.slots import shot_to_slot
from schemas.models import (
    AudioRef,
    EditTrace,
    EffectType,
    Grade,
    MotionPrimitive,
    SemanticAnnotations,
    Slot,
    Template,
)

FONT_CONFIDENCE_FLAG_THRESHOLD = 0.7
GRADE_NEUTRAL_CONTRAST_TOLERANCE = 0.1  # +/-10% of the neutral value (1.0)
GRADE_NEUTRAL_SATURATION_TOLERANCE = 0.1
GRADE_NEUTRAL_TEMP_TOLERANCE = 20.0  # matches signals/effects.py's GRADE_TEMP_SCALE units

# --------------------------------------------------------------------------
# Unit 4.3b - adjust_template()
# --------------------------------------------------------------------------

_DURATION_SCALE_MIN = 0.5
_DURATION_SCALE_MAX = 2.0
_ENERGY_BIAS_BLEND = 0.5  # move 50% of the way toward the flex bound, not straight to it - starting heuristic
_MOTION_BUCKETS = ["low", "medium", "high"]


@dataclass
class TemplateAdjustment:
    """The small, FIXED vocabulary a caller (human, MCP agent, or L7's
    chat model) may pick from - never a raw duration_s. This function
    computes the actual new numbers; the caller only picks a knob. Same
    "constrained schema" principle as evidence gating, applied to L3 math
    instead of L2 claims."""

    global_duration_scale: Optional[float] = None
    energy_bias: Optional[Literal["punchier", "calmer"]] = None
    slot_overrides: Optional[dict[str, dict]] = None

    def __post_init__(self) -> None:
        if self.global_duration_scale is not None and not (
            _DURATION_SCALE_MIN <= self.global_duration_scale <= _DURATION_SCALE_MAX
        ):
            raise ValueError(
                f"global_duration_scale must be in [{_DURATION_SCALE_MIN}, {_DURATION_SCALE_MAX}], "
                f"got {self.global_duration_scale} - reject rather than silently clamp, per this "
                "unit's own instruction, so a caller passing a nonsense value finds out immediately."
            )
        for slot_id, override in (self.slot_overrides or {}).items():
            unknown_keys = set(override) - {"duration_scale", "energy_bias"}
            if unknown_keys:
                raise ValueError(f"slot_overrides[{slot_id!r}] has unknown key(s) {sorted(unknown_keys)}")
            scale = override.get("duration_scale")
            if scale is not None and not (_DURATION_SCALE_MIN <= scale <= _DURATION_SCALE_MAX):
                raise ValueError(
                    f"slot_overrides[{slot_id!r}]['duration_scale'] must be in "
                    f"[{_DURATION_SCALE_MIN}, {_DURATION_SCALE_MAX}], got {scale}"
                )


def _bump_motion_bucket(current: str | None, direction: Literal["punchier", "calmer"]) -> str | None:
    if current not in _MOTION_BUCKETS:
        return current  # unset/unrecognized - nothing to bump, never invent a bucket
    index = _MOTION_BUCKETS.index(current)
    index = min(index + 1, len(_MOTION_BUCKETS) - 1) if direction == "punchier" else max(index - 1, 0)
    return _MOTION_BUCKETS[index]


def _scale_slot(slot: Slot, scale: float) -> Slot:
    return slot.model_copy(
        update={
            "duration_s": slot.duration_s * scale,
            "duration_flex": slot.duration_flex.model_copy(
                update={"min_s": slot.duration_flex.min_s * scale, "max_s": slot.duration_flex.max_s * scale}
            ),
        }
    )


def _apply_energy_bias(slot: Slot, bias: Literal["punchier", "calmer"]) -> Slot:
    """Moves duration_s partway toward the flex bound in the requested
    direction and bumps motion_pref one bucket the same direction. Only
    remaps EXISTING fields - never adds a motion primitive or effect the
    shot doesn't already have (the "LLM never measures" rule extended to
    L3 math, per this unit's own instruction)."""
    target = slot.duration_flex.min_s if bias == "punchier" else slot.duration_flex.max_s
    new_duration_s = slot.duration_s + (target - slot.duration_s) * _ENERGY_BIAS_BLEND
    new_motion_pref = _bump_motion_bucket(slot.requirements.motion_pref, bias)
    return slot.model_copy(
        update={
            "duration_s": new_duration_s,
            "requirements": slot.requirements.model_copy(update={"motion_pref": new_motion_pref}),
        }
    )


def _apply_slot_override(slot: Slot, override: dict | None) -> Slot:
    if override is None:
        return slot
    if "duration_scale" in override:
        slot = _scale_slot(slot, override["duration_scale"])
    if "energy_bias" in override:
        slot = _apply_energy_bias(slot, override["energy_bias"])
    return slot


def _resnap_against_beat_grid(slots: list[Slot], template: Template) -> list[Slot]:
    """Re-runs Unit 2.2's beat-snap for every slot in timeline order so
    rescaled durations still land on beats where possible - reused, not
    re-derived (same timeline-cursor pattern as matcher.assign.match_assets:
    a slot's position on the TEMPLATE's own timeline, not a position
    within any bound asset)."""
    resnapped = []
    timeline_cursor_s = 0.0
    for slot in slots:
        snapped_duration_s, _was_snapped = snap_duration_to_beat(
            min_s=slot.duration_flex.min_s,
            max_s=slot.duration_flex.max_s,
            nominal_s=slot.duration_s,
            t_start_s=timeline_cursor_s,
            beat_grid_s=template.audio_ref.beat_grid_s,
            median_cut_offset_frames=template.audio_ref.median_cut_offset_frames,
            fps=template.source_fps,
        )
        timeline_cursor_s += snapped_duration_s
        resnapped.append(slot.model_copy(update={"duration_s": snapped_duration_s}))
    return resnapped


def adjust_template(template: Template, changes: TemplateAdjustment) -> Template:
    """Pure function - no MCP/business-logic mixed in (recut_mcp.tools.adjust_template
    is the thin wrapper, Unit 4.3b). Returns a NEW Template
    (derived_from=template.template_id) - never mutates `template` in place.
    """
    slots = list(template.slots)

    if changes.global_duration_scale is not None:
        slots = [_scale_slot(s, changes.global_duration_scale) for s in slots]
        slots = _resnap_against_beat_grid(slots, template)

    if changes.energy_bias is not None:
        slots = [_apply_energy_bias(s, changes.energy_bias) for s in slots]

    if changes.slot_overrides:
        slots = [_apply_slot_override(s, changes.slot_overrides.get(s.slot_id)) for s in slots]

    return template.model_copy(update={"slots": slots, "template_id": None, "derived_from": template.template_id})


def _is_grade_non_neutral(grade: Grade) -> bool:
    """A grade "present" worth flagging - close to neutral (1.0/1.0/0.0)
    means there's nothing meaningful being lost by not applying it."""
    return (
        abs(grade.contrast - 1.0) > GRADE_NEUTRAL_CONTRAST_TOLERANCE
        or abs(grade.saturation - 1.0) > GRADE_NEUTRAL_SATURATION_TOLERANCE
        or abs(grade.temp) > GRADE_NEUTRAL_TEMP_TOLERANCE
    )


def compile_template(trace: EditTrace, *, semantics: SemanticAnnotations | None = None) -> Template:
    """Builds slots (compiler.slots.shot_to_slot per shot), builds the
    AudioRef (never an embedded file - see schemas.models.AudioRef and
    DESIGN_NOTES.md "Rights posture"), and collects confidence_flags from
    every low-confidence estimate encountered (font guesses, speed-ramp
    linearization, grade-not-applied, etc) so render/ can surface them in
    the render report (spec sec 7.3).
    """
    confidence_flags: list[str] = []
    slots = []

    for i, shot in enumerate(trace.shots, start=1):
        annotation = None
        if semantics is not None:
            annotation = next((a for a in semantics.shots if a.shot_id == shot.id), None)

        slot = shot_to_slot(shot, i, annotation=annotation, beat_grid_s=trace.audio.beat_grid_s)
        slots.append(slot)

        if shot.motion.primitive == MotionPrimitive.keyframed:
            confidence_flags.append(f"{slot.slot_id}: motion could not be fit to a primitive - raw keyframes used")

        for effect in shot.effects:
            if effect.type == EffectType.speed_ramp:
                confidence_flags.append(
                    f"{slot.slot_id}: speed ramp is approximate (confidence {effect.confidence:.2f})"
                )

        if _is_grade_non_neutral(shot.grade):
            confidence_flags.append(f"{slot.slot_id}: color grade detected but not applied in this render")

    for layer in trace.text_layers:
        if layer.style.font_confidence < FONT_CONFIDENCE_FLAG_THRESHOLD:
            confidence_flags.append(
                f"text layer {layer.id}: font guess '{layer.style.font_guess}' "
                f"has low confidence ({layer.style.font_confidence:.2f})"
            )

    audio_ref = AudioRef(
        beat_grid_s=trace.audio.beat_grid_s,
        median_cut_offset_frames=trace.audio.median_cut_offset_frames,
    )

    return Template(
        source_trace_hash=trace.source.hash,
        source_fps=trace.source.fps,
        slots=slots,
        audio_ref=audio_ref,
        text_layers=trace.text_layers,
        confidence_flags=confidence_flags,
    )
