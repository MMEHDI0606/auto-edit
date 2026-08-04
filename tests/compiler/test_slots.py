"""
Unit 2.1 done criteria: shot_to_slot() on synthetic Shots produces slots
whose human_instruction reads as sensible plain English and never states
a fact not visibly true in the source shot; motion_pref/duration_flex
bucketing behave as specified.
"""

from __future__ import annotations

from schemas.models import (
    EffectType,
    Grade,
    MotionCurve,
    MotionPrimitive,
    Shot,
    ShotContent,
    ShotEffect,
    Transition,
    TransitionType,
)
from compiler.slots import derive_duration_flex, generate_human_instruction, shot_to_slot


def _shot(
    t_in=0.0,
    t_out=1.2,
    primitive=MotionPrimitive.static,
    effects=None,
    has_face=None,
    shot_type=None,
    out_transition_type=TransitionType.cut,
    direction=None,
    duration_f=0,
) -> Shot:
    return Shot(
        id="s1",
        t_in=t_in,
        t_out=t_out,
        in_transition=Transition(type=TransitionType.cut),
        out_transition=Transition(type=out_transition_type, direction=direction, duration_f=duration_f),
        motion=MotionCurve(primitive=primitive, residual=0.01),
        effects=effects or [],
        grade=Grade(),
        content=ShotContent(has_face=has_face, shot_type=shot_type),
    )


def test_shot_to_slot_basic_fields() -> None:
    shot = _shot(t_in=0.0, t_out=1.5)
    slot = shot_to_slot(shot, order=1)
    assert slot.slot_id == "slot_01"
    assert slot.order == 1
    assert slot.duration_s == 1.5


def test_human_instruction_mentions_only_true_facts() -> None:
    shot = _shot(primitive=MotionPrimitive.punch_in, has_face=True)
    instruction = generate_human_instruction(shot)
    assert "punch" in instruction.lower() or "zoom" in instruction.lower()
    assert "face" in instruction.lower()
    # must not claim effects that aren't present
    assert "glitch" not in instruction.lower()
    assert "shake" not in instruction.lower()


def test_human_instruction_mentions_present_effects() -> None:
    shot = _shot(effects=[ShotEffect(type=EffectType.freeze, params={"duration_f": 8}, confidence=1.0)])
    instruction = generate_human_instruction(shot)
    assert "freeze" in instruction.lower()


def test_motion_pref_static_is_low() -> None:
    shot = _shot(primitive=MotionPrimitive.static)
    slot = shot_to_slot(shot, order=1)
    assert slot.requirements.motion_pref == "low"


def test_motion_pref_high_shake_overrides_to_high() -> None:
    shot = _shot(
        primitive=MotionPrimitive.punch_in,
        effects=[ShotEffect(type=EffectType.shake, params={"amplitude_px": 10.0, "freq_hz": 8.0}, confidence=1.0)],
    )
    slot = shot_to_slot(shot, order=1)
    assert slot.requirements.motion_pref == "high"


def test_motion_pref_ramped_without_shake_is_medium() -> None:
    shot = _shot(primitive=MotionPrimitive.pan)
    slot = shot_to_slot(shot, order=1)
    assert slot.requirements.motion_pref == "medium"


def test_needs_face_reflects_content() -> None:
    assert shot_to_slot(_shot(has_face=True), order=1).requirements.needs_face is True
    assert shot_to_slot(_shot(has_face=None), order=1).requirements.needs_face is False


def test_out_transition_id_includes_direction_and_duration() -> None:
    shot = _shot(out_transition_type=TransitionType.whip_pan, direction="left", duration_f=4)
    slot = shot_to_slot(shot, order=1)
    assert slot.applied.out_transition == "whip_pan_left_4f"


def test_duration_flex_window_is_plus_minus_25_percent() -> None:
    shot = _shot(t_in=0.0, t_out=2.0)
    flex = derive_duration_flex(shot, beat_grid_s=[])
    assert flex["min_s"] == 1.5
    assert flex["max_s"] == 2.5
    assert flex["snap"] == "none"


def test_duration_flex_snaps_when_out_point_near_beat() -> None:
    shot = _shot(t_in=0.0, t_out=1.0)
    flex = derive_duration_flex(shot, beat_grid_s=[0.5, 1.01, 1.5])
    assert flex["snap"] == "beat"


def test_duration_flex_does_not_snap_when_far_from_any_beat() -> None:
    shot = _shot(t_in=0.0, t_out=1.0)
    flex = derive_duration_flex(shot, beat_grid_s=[0.5, 2.0])
    assert flex["snap"] == "none"


def test_grade_ref_is_a_stable_placeholder_not_none() -> None:
    slot = shot_to_slot(_shot(), order=1)
    assert slot.applied.grade_ref is not None
    assert "s1" in slot.applied.grade_ref


def test_shot_effects_carry_through_to_slot_applied() -> None:
    # Regression guard: SlotApplied originally had no effects field at all,
    # so every detected freeze/shake/flash/rgb_split/speed_ramp effect from
    # Phase 1 was silently dropped during compilation - no render engine
    # could ever see them.
    effect = ShotEffect(type=EffectType.shake, params={"amplitude_px": 5.0, "freq_hz": 8.0}, confidence=1.0)
    shot = _shot(effects=[effect])
    slot = shot_to_slot(shot, order=1)
    assert len(slot.applied.effects) == 1
    assert slot.applied.effects[0].type == EffectType.shake
