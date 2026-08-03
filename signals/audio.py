"""
L1 - audio analysis: tempo/beat grid, transcript, speech/music separation,
cut-to-beat alignment. See RECUT_SPEC.md sec 3.4.

Notable non-obvious requirement: `median_cut_offset_frames` must NOT be
snapped to zero. Editors habitually cut 1-3 frames before the beat: this
offset is a stylistic signal that must be measured and preserved into the
Edit Trace and later honored by the matcher's beat-snap logic
(matcher/assign.py, compiler/beat_snap.py) - snapping to exactly on-beat is
a correctness bug here, not a simplification.
"""

from __future__ import annotations

from pathlib import Path

from schemas.models import AudioTrace


def extract_beat_grid(wav_path: Path) -> tuple[float, list[float]]:
    """librosa.beat_track -> (tempo_bpm, beat_grid_s)."""
    raise NotImplementedError


def extract_sections(wav_path: Path) -> list[dict]:
    """Spectral-clustering segmentation -> [{t_in, t_out, label}, ...]
    (intro/verse/drop-style labels)."""
    raise NotImplementedError


def transcribe(wav_path: Path) -> list[dict]:
    """faster-whisper with word timestamps -> [{t, word, conf}, ...]."""
    raise NotImplementedError


def separate_speech_music(wav_path: Path) -> tuple[Path, Path]:
    """Demucs stem split -> (speech_stem_path, music_stem_path). Used so
    text.py's role classifier can tell captions (matches speech) from
    lyrics (matches music, not speech) apart."""
    raise NotImplementedError


def compute_beat_lock(cut_times_s: list[float], beat_grid_s: list[float]) -> tuple[float, int]:
    """Returns (beat_lock_ratio, median_cut_offset_frames) - see module
    docstring for why the offset must be signed and preserved, not
    normalized away."""
    raise NotImplementedError


def analyze_audio(wav_path: Path, cut_times_s: list[float]) -> AudioTrace:
    """Top-level entry point used by trace_builder.py."""
    raise NotImplementedError
