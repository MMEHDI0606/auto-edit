"""
Unit 1.1 done criteria: normalize() on a real (synthetic, license-free)
fixture produces a constant-fps output, verified by re-probing it and
confirming r_frame_rate == avg_frame_rate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingest.normalize import normalize
from ingest.probe import probe_media

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


@pytest.fixture(scope="module")
def normalize_result(tmp_path_factory):
    if not FIXTURE.exists():
        pytest.skip(
            "run `python tests/fixtures/make_synthetic_clip.py` first to generate the fixture"
        )
    out_dir = tmp_path_factory.mktemp("normalize_out")
    return normalize(FIXTURE, out_dir, fps=30, width=1080, height=1920, crf=18)


def test_normalize_produces_cfr_output(normalize_result) -> None:
    assert normalize_result.normalized_path.exists()
    reprobe = probe_media(normalize_result.normalized_path)
    assert reprobe.is_vfr is False
    assert abs(reprobe.fps - 30.0) < 0.1


def test_normalize_extracts_wav(normalize_result) -> None:
    assert normalize_result.wav_path.exists()
    assert normalize_result.wav_path.stat().st_size > 0


def test_normalize_reports_source_was_not_vfr(normalize_result) -> None:
    # The synthetic fixture is CFR from birth (see make_synthetic_clip.py
    # docstring) - this asserts the non-VFR (identity time-map) branch runs
    # without error, not that VFR detection itself is exercised here.
    assert normalize_result.was_vfr is False
    assert len(normalize_result.original_to_normalized_time_map) >= 2


def test_probe_media_reads_synthetic_fixture_dimensions() -> None:
    if not FIXTURE.exists():
        pytest.skip("synthetic fixture not generated")
    result = probe_media(FIXTURE)
    assert result.width == 1080
    assert result.height == 1920
    assert result.has_audio is True
