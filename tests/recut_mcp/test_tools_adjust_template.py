"""
Unit 4.3b done criteria (MCP wrapper variant): adjust_template(template_id,
{"global_duration_scale": 99}) - out of the [0.5, 2.0] bound - raises a
clear validation error via the MCP wrapper, not a silent clamp.
"""

from __future__ import annotations

import pytest

from api.store import TemplateStore
from recut_mcp.tools import adjust_template
from schemas.models import AudioRef, DurationFlex, MotionCurve, MotionPrimitive, Slot, SlotApplied, SlotRequirements, Template


def _template() -> Template:
    return Template(
        source_trace_hash="deadbeef",
        source_fps=30,
        slots=[
            Slot(
                slot_id="slot_01",
                order=1,
                duration_s=1.0,
                duration_flex=DurationFlex(min_s=0.5, max_s=1.5, snap="none"),
                requirements=SlotRequirements(),
                applied=SlotApplied(motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01)),
                human_instruction="test",
            )
        ],
        audio_ref=AudioRef(),
    )


def test_adjust_template_returns_a_new_template_id(fake_redis_server) -> None:
    template_id = TemplateStore().create(_template())

    result = adjust_template(template_id, {"global_duration_scale": 1.25})

    assert "new_template_id" in result
    assert result["new_template_id"] != template_id
    new_template = TemplateStore().get(result["new_template_id"])
    assert new_template.slots[0].duration_s == pytest.approx(1.25)
    assert new_template.derived_from == template_id


def test_adjust_template_out_of_range_scale_raises_clear_error(fake_redis_server) -> None:
    template_id = TemplateStore().create(_template())
    with pytest.raises(ValueError):
        adjust_template(template_id, {"global_duration_scale": 99})


def test_adjust_template_unknown_top_level_key_raises(fake_redis_server) -> None:
    template_id = TemplateStore().create(_template())
    with pytest.raises(ValueError):
        adjust_template(template_id, {"not_a_real_knob": 1})


def test_adjust_template_energy_bias(fake_redis_server) -> None:
    template_id = TemplateStore().create(_template())
    result = adjust_template(template_id, {"energy_bias": "punchier"})
    new_template = TemplateStore().get(result["new_template_id"])
    assert new_template.slots[0].duration_s < 1.0
