"""
Unit 1.7 done criteria: group_into_layers() against synthetic box
sequences (no real OCR needed) covering the three required cases:
  (a) one string persisting across frames -> one layer
  (b) two different strings back-to-back in the same screen position ->
      two separate layers (must NOT merge)
  (c) a single missed frame in the middle of a persisting string -> still
      one layer (grace window)
Plus a real sample_and_ocr() check against the synthetic fixture's known
"HOOK TEXT" overlay (Unit 1.19-style manual/real check, gated on paddleocr
being installed - see pyproject.toml `ocr` extra).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from signals.text import group_into_layers

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"
FIXTURE_META = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.meta.json"

BOX = (0.4, 0.4, 0.2, 0.1)  # same on-screen position for cases (a)/(b)/(c)
FAR_BOX = (0.05, 0.05, 0.1, 0.05)  # unrelated anchor position, kept present every frame


def test_persisting_string_forms_one_layer() -> None:
    raw_boxes = [
        {"t": 0.0, "text": "HOOK TEXT", "box": BOX, "conf": 0.9},
        {"t": 0.125, "text": "HOOK TEXT", "box": BOX, "conf": 0.9},
        {"t": 0.25, "text": "HOOK TEXT", "box": BOX, "conf": 0.9},
    ]
    layers = group_into_layers(raw_boxes)
    assert len(layers) == 1
    assert layers[0]["string"] == "HOOK TEXT"
    assert layers[0]["t_in"] == 0.0
    assert layers[0]["t_out"] == 0.25


def test_two_distinct_strings_same_position_do_not_merge() -> None:
    raw_boxes = [
        {"t": 0.0, "text": "FIRST LINE", "box": BOX, "conf": 0.9},
        {"t": 0.125, "text": "FIRST LINE", "box": BOX, "conf": 0.9},
        {"t": 0.25, "text": "SECOND LINE", "box": BOX, "conf": 0.9},
        {"t": 0.375, "text": "SECOND LINE", "box": BOX, "conf": 0.9},
    ]
    layers = group_into_layers(raw_boxes)
    assert len(layers) == 2
    strings = {l["string"] for l in layers}
    assert strings == {"FIRST LINE", "SECOND LINE"}
    first = next(l for l in layers if l["string"] == "FIRST LINE")
    second = next(l for l in layers if l["string"] == "SECOND LINE")
    assert first["t_out"] <= second["t_in"]


def test_single_missed_frame_still_one_layer_with_grace_window() -> None:
    # FAR_BOX present every frame (including t=0.125) so that timestamp is
    # a real "step" the grouper sees, even though HOOK TEXT has no
    # detection there - this is what actually exercises the grace-window
    # counter rather than the layer simply never being challenged.
    raw_boxes = [
        {"t": 0.0, "text": "HOOK TEXT", "box": BOX, "conf": 0.9},
        {"t": 0.0, "text": "anchor", "box": FAR_BOX, "conf": 0.9},
        {"t": 0.125, "text": "anchor", "box": FAR_BOX, "conf": 0.9},  # HOOK TEXT missed this frame
        {"t": 0.25, "text": "HOOK TEXT", "box": BOX, "conf": 0.9},
        {"t": 0.25, "text": "anchor", "box": FAR_BOX, "conf": 0.9},
    ]
    layers = group_into_layers(raw_boxes)
    hook_layers = [l for l in layers if l["string"] == "HOOK TEXT"]
    assert len(hook_layers) == 1
    assert hook_layers[0]["t_in"] == 0.0
    assert hook_layers[0]["t_out"] == 0.25


def test_layer_closes_after_grace_window_exceeded() -> None:
    raw_boxes = [
        {"t": 0.0, "text": "HOOK TEXT", "box": BOX, "conf": 0.9},
        {"t": 0.0, "text": "anchor", "box": FAR_BOX, "conf": 0.9},
        {"t": 0.125, "text": "anchor", "box": FAR_BOX, "conf": 0.9},  # miss 1
        {"t": 0.25, "text": "anchor", "box": FAR_BOX, "conf": 0.9},  # miss 2 - exceeds grace window
        {"t": 0.375, "text": "HOOK TEXT", "box": BOX, "conf": 0.9},  # a NEW appearance, not a continuation
        {"t": 0.375, "text": "anchor", "box": FAR_BOX, "conf": 0.9},
    ]
    layers = group_into_layers(raw_boxes)
    hook_layers = [l for l in layers if l["string"] == "HOOK TEXT"]
    assert len(hook_layers) == 2
    assert hook_layers[0]["t_out"] == 0.0
    assert hook_layers[1]["t_in"] == 0.375


def test_empty_input_returns_no_layers() -> None:
    assert group_into_layers([]) == []


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="run tests/fixtures/make_synthetic_clip.py first",
)
def test_sample_and_ocr_finds_known_text_in_synthetic_clip() -> None:
    pytest.importorskip("paddleocr")
    from signals.text import sample_and_ocr

    meta = json.loads(FIXTURE_META.read_text())
    raw_boxes = sample_and_ocr(FIXTURE, sample_fps=8)
    layers = group_into_layers(raw_boxes)

    expected_string = meta["text_layers"][0]["string"]
    assert any(_normalizes_close(l["string"], expected_string) for l in layers), (
        f"expected a layer matching {expected_string!r}, got {[l['string'] for l in layers]}"
    )


def _normalizes_close(ocr_string: str, expected: str) -> bool:
    import difflib

    return difflib.SequenceMatcher(None, ocr_string.upper(), expected.upper()).ratio() >= 0.6
