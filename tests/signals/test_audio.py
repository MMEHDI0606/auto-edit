"""
Unit 1.9 done criteria: extract_beat_grid()'s tempo, on a real (synthetic,
license-free) fixture with a known 120 BPM click track, is within ~5 BPM
of the true value (spec's own stated tolerance - tempo octave errors are a
known librosa failure mode, not something to chase perfectly in Phase 1).
extract_sections() has no specific accuracy bar (semantic labeling is L2's
job) - tested for basic structural correctness only.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from signals.audio import extract_beat_grid, extract_sections

FIXTURE_MP4 = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"
FIXTURE_META = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.meta.json"
FIXTURE_WAV = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.wav"


@pytest.fixture(scope="module")
def fixture_wav():
    if not FIXTURE_MP4.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")
    if not FIXTURE_WAV.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(FIXTURE_MP4), "-ar", "22050", "-ac", "1", str(FIXTURE_WAV)],
            check=True, capture_output=True,
        )
    return FIXTURE_WAV


def test_extract_beat_grid_tempo_within_tolerance_of_known_bpm(fixture_wav) -> None:
    meta = json.loads(FIXTURE_META.read_text())
    expected_bpm = meta["tempo_bpm"]  # 120.0, see make_synthetic_clip.py

    tempo_bpm, beat_grid_s = extract_beat_grid(fixture_wav)

    assert abs(tempo_bpm - expected_bpm) <= 5.0, f"expected ~{expected_bpm} BPM, got {tempo_bpm}"
    assert len(beat_grid_s) > 0
    assert all(0.0 <= t <= meta["duration_s"] for t in beat_grid_s)


def test_extract_sections_covers_full_duration_with_generic_labels(fixture_wav) -> None:
    meta = json.loads(FIXTURE_META.read_text())
    sections = extract_sections(fixture_wav)

    assert len(sections) >= 1
    assert sections[0]["t_in"] == pytest.approx(0.0, abs=1e-6)
    assert sections[-1]["t_out"] == pytest.approx(meta["duration_s"], abs=0.1)
    for i, section in enumerate(sections):
        assert section["label"] == f"section_{i + 1}"  # generic, never semantic
        assert section["t_in"] < section["t_out"]
    # contiguous, non-overlapping
    for a, b in zip(sections[:-1], sections[1:]):
        assert a["t_out"] == pytest.approx(b["t_in"], abs=1e-6)
