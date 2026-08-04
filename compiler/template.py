"""
L3 orchestrator - Trace (+ optional SemanticAnnotations) -> Template.
See RECUT_SPEC.md sec 5.

This is the only compiler/ entry point other packages should import.
"""

from __future__ import annotations

from compiler.slots import shot_to_slot
from schemas.models import (
    AudioRef,
    EditTrace,
    EffectType,
    Grade,
    MotionPrimitive,
    SemanticAnnotations,
    Template,
)

FONT_CONFIDENCE_FLAG_THRESHOLD = 0.7
GRADE_NEUTRAL_CONTRAST_TOLERANCE = 0.1  # +/-10% of the neutral value (1.0)
GRADE_NEUTRAL_SATURATION_TOLERANCE = 0.1
GRADE_NEUTRAL_TEMP_TOLERANCE = 20.0  # matches signals/effects.py's GRADE_TEMP_SCALE units


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
