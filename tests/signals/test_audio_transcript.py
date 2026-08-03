"""
Unit 1.10 done criteria: on a real speech clip, spot-check the transcript
against what's actually said - word-level timestamps within ~200ms is the
spec's own tolerance (loose; this feeds role classification, not a hard
metric in Unit 1.19's gate).

tests/fixtures/synthetic_speech.wav is generated locally via Windows'
built-in SAPI TTS (System.Speech), not scraped or downloaded - fully
synthetic, license-free, reproducible on any Windows dev box:

    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.SetOutputToWaveFile("tests/fixtures/synthetic_speech.wav")
    $synth.Speak("Hello there, this is a test of the transcription system.")

Not committed to git (matches *.wav in .gitignore) - regenerate locally
with the PowerShell snippet above before running this test elsewhere.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from signals.audio import transcribe

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_speech.wav"
EXPECTED_SENTENCE = "Hello there, this is a test of the transcription system."


@pytest.mark.skipif(not FIXTURE.exists(), reason="regenerate via the PowerShell snippet in this file's docstring")
def test_transcribe_matches_known_spoken_sentence() -> None:
    words = transcribe(FIXTURE)

    assert len(words) > 0
    transcribed_text = " ".join(w["word"] for w in words)
    similarity = difflib.SequenceMatcher(None, transcribed_text.lower(), EXPECTED_SENTENCE.lower()).ratio()
    assert similarity > 0.8, f"transcript {transcribed_text!r} too different from {EXPECTED_SENTENCE!r}"

    for w in words:
        assert 0.0 <= w["conf"] <= 1.0
        assert w["t"] >= 0.0

    # word timestamps must be non-decreasing
    timestamps = [w["t"] for w in words]
    assert timestamps == sorted(timestamps)
