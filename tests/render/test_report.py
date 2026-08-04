"""
Unit 2.8 done criteria: both engines format their own approximation
entries the same way ("{slot_id}: {reason}"), diffable/comparable even
though the actual content differs per engine.
"""

from __future__ import annotations

import re

from render.report import add_approximation, format_approximation

_APPROXIMATION_PATTERN = re.compile(r"^[^:]+: .+$")


def test_format_approximation_matches_slot_id_colon_reason() -> None:
    assert format_approximation("slot_01", "no asset bound") == "slot_01: no asset bound"


def test_add_approximation_appends_formatted_entry() -> None:
    approximations: list[str] = []
    add_approximation(approximations, "slot_02", "dissolve approximated as a hard cut")
    assert approximations == ["slot_02: dissolve approximated as a hard cut"]


def test_add_approximation_preserves_existing_entries() -> None:
    approximations = ["slot_01: something already flagged"]
    add_approximation(approximations, "slot_02", "another reason")
    assert approximations == ["slot_01: something already flagged", "slot_02: another reason"]


def test_format_matches_the_general_slot_id_colon_reason_shape() -> None:
    formatted = format_approximation("slot_03", "punch_in motion not rendered by ffmpeg engine (cut-only)")
    assert _APPROXIMATION_PATTERN.match(formatted)
