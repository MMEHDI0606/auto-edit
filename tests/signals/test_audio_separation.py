"""
Unit 1.11 (speech/music separation half) done criteria: separate_speech_music()
against a real speech clip should route the speech energy into the vocals
stem, not the no_vocals stem - the concrete, checkable prediction for a
pure-speech, no-music fixture.

This is a genuinely slow step on CPU (spec sec 8.5) - first run also
downloads the htdemucs model (~80MB). Uses tests/fixtures/synthetic_speech.wav
(Unit 1.10's Windows-TTS-generated fixture, not committed - see that
file's docstring to regenerate).
"""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import pytest

from signals.audio import separate_speech_music

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_speech.wav"


def _rms(path: Path) -> float:
    y, _sr = librosa.load(str(path), sr=None)
    return float(np.sqrt(np.mean(y**2)))


@pytest.mark.skipif(not FIXTURE.exists(), reason="regenerate via the PowerShell snippet in test_audio_transcript.py")
def test_separate_speech_music_routes_speech_to_vocals_stem() -> None:
    vocals_path, no_vocals_path = separate_speech_music(FIXTURE)

    assert vocals_path.exists() and vocals_path.stat().st_size > 0
    assert no_vocals_path.exists() and no_vocals_path.stat().st_size > 0

    vocals_rms = _rms(vocals_path)
    no_vocals_rms = _rms(no_vocals_path)

    # The fixture is pure speech with no music - most of the energy should
    # land in the vocals stem, not the "everything else" stem. htdemucs is
    # trained on sung vocals in a music mix, not flat TTS speech, so this
    # isn't a clean near-total separation (observed ~2.8x) - 2x is still a
    # real, meaningful signal rather than an arbitrary tight bar.
    assert vocals_rms > no_vocals_rms * 2
