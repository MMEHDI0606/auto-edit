"""
L3 - converts each Shot (+ optional SemanticShotAnnotation) into a Slot.
See RECUT_SPEC.md sec 5.1.

`human_instruction` generation is THE product surface (spec's own words:
"the human_instruction field is the product") - treat wording quality as a
first-class deliverable, not boilerplate string formatting. In Phase 1-2
(before L2 semantics exist), generate a mechanical instruction from L1
facts alone (duration, motion_pref, needs_face); in Phase 3, prefer the
LLM-authored version when semantics are available, still constrained to
only reference evidence-backed facts (same evidence-gating principle as
L2 - see semantics/gating.py).
"""

from __future__ import annotations

from schemas.models import (
    DurationFlex,
    EffectType,
    MotionPrimitive,
    SemanticShotAnnotation,
    Shot,
    Slot,
    SlotApplied,
    SlotRequirements,
    Transition,
)

DURATION_FLEX_FRACTION = 0.25  # +/-25% of shot duration - starting heuristic, retune against golden set
BEAT_SNAP_TOLERANCE_S = 1.0 / 15  # ~2 frames at 30fps - a shot's out-point this close to a beat gets snap="beat"
SHAKE_HIGH_AMPLITUDE_PX = 3.0  # above this, motion_pref buckets to "high" regardless of primitive

_MOTION_DESCRIPTIONS: dict[MotionPrimitive, str] = {
    MotionPrimitive.punch_in: "Camera punches in (zooms in) during the shot.",
    MotionPrimitive.slow_push: "Slow push-in on the subject.",
    MotionPrimitive.zoom_out_reveal: "Zooms out to reveal more of the scene.",
    MotionPrimitive.pan: "Camera pans across the frame.",
    MotionPrimitive.whip: "Fast whip motion within the shot.",
    MotionPrimitive.static: "Static, no camera motion.",
    MotionPrimitive.keyframed: "Complex camera motion.",
}

_EFFECT_DESCRIPTIONS: dict[EffectType, str] = {
    EffectType.freeze: "Includes a freeze-frame moment.",
    EffectType.shake: "Has a handheld shake feel.",
    EffectType.flash: "Has a flash/strobe hit.",
    EffectType.blur_pulse: "Has a blur-pulse transition moment.",
    EffectType.rgb_split: "Has a glitch/RGB-split effect.",
    EffectType.speed_ramp: "Includes a speed ramp (approximate timing).",
}

# Unit 3.5 - natural phrasing for common narrative roles (spec sec 4.2's
# examples). An unrecognized role string still gets a serviceable opener
# via the f-string fallback in generate_human_instruction() - this dict is
# just nicer wording for the roles worth naming explicitly, not a
# whitelist (the role has ALREADY been evidence-gated by the time it gets
# here; this module never rejects one).
_ROLE_OPENERS: dict[str, str] = {
    "hook": "This is your hook shot",
    "before_state": "This is the 'before' shot",
    "reveal": "This is your reveal shot",
    "reaction": "This is your reaction shot",
    "cta": "This is your call-to-action shot",
}


def _transition_id(transition: Transition) -> str:
    parts = [transition.type.value]
    if transition.direction:
        parts.append(transition.direction)
    if transition.duration_f:
        parts.append(f"{transition.duration_f}f")
    return "_".join(parts)


def _motion_pref(shot: Shot) -> str:
    if shot.motion.primitive == MotionPrimitive.static:
        return "low"
    shake_amplitude = next(
        (e.params.get("amplitude_px", 0.0) for e in shot.effects if e.type == EffectType.shake), 0.0
    )
    if shake_amplitude > SHAKE_HIGH_AMPLITUDE_PX:
        return "high"
    return "medium"


def derive_duration_flex(shot: Shot, *, beat_grid_s: list[float]) -> dict:
    """min_s/max_s bounds and snap policy. See compiler/beat_snap.py for
    the actual snapping algorithm consumed by the matcher - this function
    only decides the flex WINDOW, not how a bound asset's cut point gets
    snapped at match time."""
    duration_s = shot.t_out - shot.t_in
    min_s = duration_s * (1 - DURATION_FLEX_FRACTION)
    max_s = duration_s * (1 + DURATION_FLEX_FRACTION)

    snap = "none"
    if beat_grid_s:
        nearest = min(beat_grid_s, key=lambda b: abs(b - shot.t_out))
        if abs(nearest - shot.t_out) <= BEAT_SNAP_TOLERANCE_S:
            snap = "beat"

    return {"min_s": min_s, "max_s": max_s, "snap": snap}


def generate_human_instruction(shot: Shot, *, annotation: SemanticShotAnnotation | None = None) -> str:
    """Mechanical (L1-only) instruction when annotation is None; richer
    phrasing when semantic role/content is available (Unit 3.5). Must
    never state a fact not backed by shot.effects/motion/content, or on
    the annotation - same rule as L2.

    `annotation` is assumed to have ALREADY passed semantics/gating.py's
    validate_annotation() by the time it reaches this function (Units 3.1/
    3.4's job, not this one's) - this function trusts annotation.role as
    given, but never derives or introduces a NEW unvalidated claim of its
    own on top of it.
    """
    duration_s = shot.t_out - shot.t_in

    if annotation is not None and annotation.role:
        opener = _ROLE_OPENERS.get(annotation.role, f"This is your {annotation.role} shot")
        parts = [f"{opener} (~{duration_s:.1f}s)."]
    else:
        parts = [f"Drop a clip here (~{duration_s:.1f}s)."]

    motion_desc = _MOTION_DESCRIPTIONS.get(shot.motion.primitive)
    if motion_desc:
        parts.append(motion_desc)

    if shot.content.has_face:
        parts.append("Needs a visible face.")

    for effect in shot.effects:
        effect_desc = _EFFECT_DESCRIPTIONS.get(effect.type)
        if effect_desc:
            parts.append(effect_desc)

    return " ".join(parts)


def shot_to_slot(
    shot: Shot,
    order: int,
    *,
    annotation: SemanticShotAnnotation | None = None,
    beat_grid_s: list[float] | None = None,
) -> Slot:
    requirements = SlotRequirements(
        needs_face=bool(shot.content.has_face),
        motion_pref=_motion_pref(shot),
        shot_type_pref=[shot.content.shot_type] if shot.content.shot_type else [],
        role=annotation.role if annotation is not None else None,
    )

    applied = SlotApplied(
        motion=shot.motion,
        # Placeholder id, not a real grade reference - v1 stores grade
        # stats but does not apply them (DESIGN_NOTES.md sec 8). Kept as a
        # stable string per-shot so a future grade-application feature has
        # something to key off without a schema change.
        grade_ref=f"grade_ref_{shot.id}",
        out_transition=_transition_id(shot.out_transition),
        effects=shot.effects,
    )

    return Slot(
        slot_id=f"slot_{order:02d}",
        order=order,
        duration_s=shot.t_out - shot.t_in,
        duration_flex=DurationFlex(**derive_duration_flex(shot, beat_grid_s=beat_grid_s or [])),
        requirements=requirements,
        applied=applied,
        human_instruction=generate_human_instruction(shot, annotation=annotation),
    )
