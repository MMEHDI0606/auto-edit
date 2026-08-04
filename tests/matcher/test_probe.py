"""
Unit 3.6 done criteria: "running extract_asset_features against 5-10
varied local test clips (different orientations, with/without faces,
with/without speech) produces plausible AssetFeatures for each - spot
check by eye." The full 5-10-clip variety needs real donated footage,
blocked the same way as the golden-set video (see eval/golden/NEEDS_INPUT.md)
- NOT something an agent can fabricate (a drawn "face" would not exercise
the real Haar-cascade detection path at all).

What CAN be verified without real footage: the two axes that matter most
(has_face, has_speech) each get one REAL positive and one real negative
example. The face-positive case uses a real (public-domain NASA) photo via
skimage.data.astronaut() - see tests/fixtures/make_face_clip.py for why a
drawn shape would not do - muxed with the project's existing real
Windows-SAPI TTS speech fixture. The negative case reuses the existing
Phase-1 synthetic_clip.mp4 fixture (solid colors, click-track audio - no
face, no real speech).

Marked slow: loads real CLIP weights + runs real faster-whisper inference.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matcher.probe import extract_asset_features

FACE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_face_clip.mp4"
NO_FACE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


@pytest.mark.slow
def test_extract_asset_features_detects_a_real_face_and_speech() -> None:
    if not FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_face_clip.py first")

    features = extract_asset_features(FACE_FIXTURE, "face_clip")

    assert features.asset_id == "face_clip"
    assert features.asset_path == str(FACE_FIXTURE)
    assert features.has_face is True
    assert features.shot_type_guess in ("closeup", "wide")
    assert features.orientation == "square"  # astronaut() is 512x512
    assert features.has_speech is True  # real TTS speech muxed in
    assert len(features.clip_embedding) > 0
    assert features.duration_s == pytest.approx(5.19, abs=0.1)


@pytest.mark.slow
def test_extract_asset_features_on_no_face_no_speech_clip() -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    features = extract_asset_features(NO_FACE_FIXTURE, "no_face_clip")

    assert features.has_face is False
    assert features.shot_type_guess == "wide"
    assert features.orientation == "vertical"  # 1080x1920
    # BUG FOUND (see matcher/probe.py's _has_alphanumeric comment): without
    # the alphanumeric filter, faster-whisper hallucinates an "..." token
    # at >0.78 confidence against this click-track audio, which would have
    # made this assert True incorrectly.
    assert features.has_speech is False
    assert 0.0 <= features.motion_score <= 1.0
    assert len(features.clip_embedding) > 0


@pytest.mark.slow
def test_clip_embedding_is_l2_normalized() -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    features = extract_asset_features(NO_FACE_FIXTURE, "no_face_clip")
    norm = sum(x * x for x in features.clip_embedding) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-3)
