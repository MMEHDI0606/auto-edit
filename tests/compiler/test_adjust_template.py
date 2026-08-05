"""
Unit 4.3b done criteria: global_duration_scale=1.25 produces a new
template whose slot durations are all ~25% longer (within beat-snap
tolerance) and whose derived_from points at the source; energy_bias=
"punchier" on a template with mixed motion_pref values measurably shifts
durations shorter and motion_pref buckets upward without adding any
effect not already present on the source shots (asserted explicitly - the
regression this unit exists to prevent); an out-of-range
global_duration_scale raises a clear validation error, not a silent clamp.
"""

from __future__ import annotations

import pytest

from compiler.template import TemplateAdjustment, adjust_template
from schemas.models import (
    AudioRef,
    DurationFlex,
    EffectType,
    MotionCurve,
    MotionPrimitive,
    Slot,
    SlotApplied,
    SlotRequirements,
    Template,
)


def _slot(slot_id: str, order: int, duration_s: float, *, motion_pref: str | None = None, effects=None) -> Slot:
    return Slot(
        slot_id=slot_id,
        order=order,
        duration_s=duration_s,
        duration_flex=DurationFlex(min_s=duration_s * 0.5, max_s=duration_s * 1.5, snap="none"),
        requirements=SlotRequirements(motion_pref=motion_pref),
        applied=SlotApplied(motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01), effects=effects or []),
        human_instruction="test slot",
    )


def _template(slots: list[Slot], *, template_id: str | None = "src-template-1", beat_grid_s=None) -> Template:
    return Template(
        template_id=template_id,
        source_trace_hash="deadbeef",
        source_fps=30,
        slots=slots,
        audio_ref=AudioRef(beat_grid_s=beat_grid_s or []),
    )


def test_global_duration_scale_lengthens_every_slot_by_the_scale_factor() -> None:
    template = _template([_slot("slot_01", 1, 1.0), _slot("slot_02", 2, 2.0)])

    result = adjust_template(template, TemplateAdjustment(global_duration_scale=1.25))

    # No beat grid -> snap_duration_to_beat falls back to the (scaled)
    # nominal duration unchanged, so the scale factor holds exactly here.
    assert result.slots[0].duration_s == pytest.approx(1.25)
    assert result.slots[1].duration_s == pytest.approx(2.5)


def test_global_duration_scale_sets_derived_from_to_source_template_id() -> None:
    template = _template([_slot("slot_01", 1, 1.0)], template_id="src-template-1")
    result = adjust_template(template, TemplateAdjustment(global_duration_scale=1.25))
    assert result.derived_from == "src-template-1"
    assert result.template_id is None  # not yet persisted - TemplateStore.create() assigns a fresh one


def test_global_duration_scale_also_scales_duration_flex_bounds() -> None:
    template = _template([_slot("slot_01", 1, 1.0)])  # flex = [0.5, 1.5]
    result = adjust_template(template, TemplateAdjustment(global_duration_scale=2.0))
    assert result.slots[0].duration_flex.min_s == pytest.approx(1.0)
    assert result.slots[0].duration_flex.max_s == pytest.approx(3.0)


def test_global_duration_scale_out_of_range_raises_instead_of_clamping() -> None:
    with pytest.raises(ValueError):
        TemplateAdjustment(global_duration_scale=99.0)
    with pytest.raises(ValueError):
        TemplateAdjustment(global_duration_scale=0.1)


def test_energy_bias_punchier_shortens_duration_toward_flex_min() -> None:
    template = _template([_slot("slot_01", 1, 1.0)])  # flex min = 0.5
    result = adjust_template(template, TemplateAdjustment(energy_bias="punchier"))
    # Blended 50% of the way from 1.0 toward 0.5 -> 0.75.
    assert result.slots[0].duration_s == pytest.approx(0.75)


def test_energy_bias_calmer_lengthens_duration_toward_flex_max() -> None:
    template = _template([_slot("slot_01", 1, 1.0)])  # flex max = 1.5
    result = adjust_template(template, TemplateAdjustment(energy_bias="calmer"))
    assert result.slots[0].duration_s == pytest.approx(1.25)


def test_energy_bias_punchier_bumps_motion_pref_bucket_upward() -> None:
    template = _template(
        [_slot("slot_01", 1, 1.0, motion_pref="low"), _slot("slot_02", 2, 1.0, motion_pref="medium")]
    )
    result = adjust_template(template, TemplateAdjustment(energy_bias="punchier"))
    assert result.slots[0].requirements.motion_pref == "medium"
    assert result.slots[1].requirements.motion_pref == "high"


def test_energy_bias_calmer_bumps_motion_pref_bucket_downward() -> None:
    template = _template([_slot("slot_01", 1, 1.0, motion_pref="high")])
    result = adjust_template(template, TemplateAdjustment(energy_bias="calmer"))
    assert result.slots[0].requirements.motion_pref == "medium"


def test_energy_bias_never_adds_an_effect_not_already_present() -> None:
    """The regression this unit exists to prevent - punchier/calmer must
    only remap existing fields, never invent a new evidenced claim."""
    template = _template(
        [
            _slot("slot_01", 1, 1.0, motion_pref="low", effects=[]),
            _slot(
                "slot_02",
                2,
                1.0,
                motion_pref="low",
                effects=[{"type": EffectType.freeze, "params": {}, "confidence": 1.0}],
            ),
        ]
    )

    result = adjust_template(template, TemplateAdjustment(energy_bias="punchier"))

    assert result.slots[0].applied.effects == []
    assert [e.type for e in result.slots[1].applied.effects] == [EffectType.freeze]


def test_slot_overrides_apply_only_to_the_named_slot_after_global_changes() -> None:
    template = _template([_slot("slot_01", 1, 1.0), _slot("slot_02", 2, 1.0)])

    result = adjust_template(
        template,
        TemplateAdjustment(global_duration_scale=1.25, slot_overrides={"slot_02": {"duration_scale": 2.0}}),
    )

    assert result.slots[0].duration_s == pytest.approx(1.25)  # only the global scale
    assert result.slots[1].duration_s == pytest.approx(1.25 * 2.0)  # global scale, then the override on top


def test_slot_overrides_rejects_unknown_key() -> None:
    with pytest.raises(ValueError):
        TemplateAdjustment(slot_overrides={"slot_01": {"not_a_real_knob": 1}})


def test_no_changes_leaves_slots_unchanged() -> None:
    template = _template([_slot("slot_01", 1, 1.0, motion_pref="medium")])
    result = adjust_template(template, TemplateAdjustment())
    assert result.slots[0].duration_s == pytest.approx(1.0)
    assert result.slots[0].requirements.motion_pref == "medium"
