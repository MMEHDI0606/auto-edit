"""
Unit 1.4 done criteria: reconcile_detectors() unit test against synthetic
boundary lists (no real video), plus detect_boundaries() run against the
real (synthetic, license-free) fixture clip to confirm rapid/known cuts
are found and not merged away by min_scene_len tuning.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from signals.cuts import detect_boundaries, reconcile_detectors

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"
FIXTURE_META = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.meta.json"


def test_reconcile_detectors_merges_near_duplicate_boundaries() -> None:
    adaptive = [1.0, 1.03, 5.0]
    content = [1.01, 5.0, 8.2]
    merged = reconcile_detectors(adaptive, content, fps=30)
    assert merged == [1.0, 5.0, 8.2]


def test_reconcile_detectors_keeps_distinct_boundaries_apart() -> None:
    # 0.1s apart at fps=30 (tolerance ~0.033s) - must NOT merge.
    merged = reconcile_detectors([1.0], [1.1], fps=30)
    assert merged == [1.0, 1.1]


def test_reconcile_detectors_empty_input() -> None:
    assert reconcile_detectors([], [], fps=30) == []


def test_detect_boundaries_finds_known_cuts_in_synthetic_clip() -> None:
    if not FIXTURE.exists():
        pytest.skip("run `python tests/fixtures/make_synthetic_clip.py` first")
    meta = json.loads(FIXTURE_META.read_text())
    expected_cuts = meta["cuts_s"]  # [1.2, 2.0]

    detected = detect_boundaries(FIXTURE, min_scene_len_frames=3)

    # Every expected cut must have a detected boundary within ~2 frames.
    tolerance_s = 2 / meta["fps"]
    for expected_t in expected_cuts:
        assert any(abs(d - expected_t) <= tolerance_s for d in detected), (
            f"expected cut at {expected_t}s not found in detected boundaries {detected}"
        )
    # And detection must not have missed/merged them into a single boundary -
    # this is the specific min_scene_len failure mode spec sec 3.1 warns about.
    assert len(detected) >= len(expected_cuts)
