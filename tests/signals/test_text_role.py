"""
Unit 1.11 (text-role half) done criteria: manual review across >=2 of the
6 roles, with the concrete spec sec 8.3 "burned-in captions vs speech"
test case - a caption AND a lyric layer in the same video must not be
confused for each other.
"""

from __future__ import annotations

from signals.text import classify_role

VIDEO_DURATION_S = 20.0
TRANSCRIPT = [
    {"t": 5.0, "word": "hello", "conf": 0.9},
    {"t": 5.3, "word": "world", "conf": 0.9},
]


def _layer(t_in, t_out, string, box=(0.5, 0.5, 0.4, 0.06)):
    return {"t_in": t_in, "t_out": t_out, "string": string, "box": box}


def test_caption_burnin_matches_overlapping_transcript() -> None:
    layer = _layer(5.0, 5.5, "hello world")
    role, confidence = classify_role(
        layer, transcript_words=TRANSCRIPT, music_active=False, video_duration_s=VIDEO_DURATION_S
    )
    assert role == "caption_burnin"
    assert confidence > 0.5


def test_lyric_when_music_active_and_no_speech_overlap() -> None:
    # No overlapping transcript words at this timestamp (transcript is at 5-5.3s).
    layer = _layer(12.0, 12.8, "some lyric line")
    role, _confidence = classify_role(
        layer, transcript_words=TRANSCRIPT, music_active=True, video_duration_s=VIDEO_DURATION_S
    )
    assert role == "lyric"


def test_caption_and_lyric_coexist_without_confusion_in_same_video() -> None:
    # The exact spec sec 8.3 scenario: a caption layer (matches speech) and
    # a lyric layer (matches music, not speech) present in the SAME video,
    # sharing the same transcript_words/music_active inputs.
    caption_layer = _layer(5.0, 5.5, "hello world")
    lyric_layer = _layer(12.0, 12.8, "some lyric line")

    caption_role, _ = classify_role(
        caption_layer, transcript_words=TRANSCRIPT, music_active=True, video_duration_s=VIDEO_DURATION_S
    )
    lyric_role, _ = classify_role(
        lyric_layer, transcript_words=TRANSCRIPT, music_active=True, video_duration_s=VIDEO_DURATION_S
    )
    assert caption_role == "caption_burnin"
    assert lyric_role == "lyric"
    assert caption_role != lyric_role


def test_hook_title_early_and_prominent() -> None:
    layer = _layer(0.5, 2.0, "POV: you finally", box=(0.1, 0.2, 0.8, 0.1))
    role, _confidence = classify_role(
        layer, transcript_words=[], music_active=False, video_duration_s=VIDEO_DURATION_S, median_size_rel=0.05
    )
    assert role == "hook_title"


def test_cta_short_string_near_end() -> None:
    layer = _layer(18.0, 19.0, "Follow now")
    role, _confidence = classify_role(layer, transcript_words=[], music_active=False, video_duration_s=VIDEO_DURATION_S)
    assert role == "cta"


def test_watermark_bottom_corner_persistent() -> None:
    layer = _layer(0.0, 19.5, "@creator", box=(0.87, 0.9, 0.1, 0.08))
    role, _confidence = classify_role(layer, transcript_words=[], music_active=False, video_duration_s=VIDEO_DURATION_S)
    assert role == "watermark"


def test_defaults_to_label_when_nothing_matches() -> None:
    layer = _layer(9.0, 9.5, "just a caption with no other signal", box=(0.4, 0.5, 0.3, 0.05))
    role, confidence = classify_role(
        layer, transcript_words=[], music_active=False, video_duration_s=VIDEO_DURATION_S, median_size_rel=0.1
    )
    assert role == "label"
    assert confidence < 0.5
