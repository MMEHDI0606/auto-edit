"""
Unit 2.6 done criteria: nearest_fallback_primitive("zoom_out_reveal")
returns "punch_in", and every value in schemas.models.MotionPrimitive has
SOME fallback entry - the function must never raise or return None.
"""

from __future__ import annotations

from render.effects_library.primitives import nearest_fallback_primitive
from schemas.models import MotionPrimitive


def test_zoom_out_reveal_falls_back_to_punch_in() -> None:
    assert nearest_fallback_primitive("zoom_out_reveal") == "punch_in"


def test_every_motion_primitive_value_has_a_fallback_entry() -> None:
    for primitive in MotionPrimitive:
        result = nearest_fallback_primitive(primitive.value)
        assert result is not None
        assert isinstance(result, str)
        assert result != ""


def test_unknown_name_returns_safe_default_not_none() -> None:
    result = nearest_fallback_primitive("totally_made_up_primitive_name")
    assert result is not None
    assert isinstance(result, str)
