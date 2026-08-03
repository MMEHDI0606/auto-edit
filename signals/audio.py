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

import librosa
import numpy as np

from schemas.models import AudioTrace

# Unit 1.9 tunables - see module docstring / INSTRUCTIONS.md Unit 1.9.
_SECTION_TARGET_LENGTH_S = 8.0  # heuristic: aim for ~1 section per 8s; retune against golden set (Unit 1.19)
_SECTION_MAX_COUNT = 8


def extract_beat_grid(wav_path: Path) -> tuple[float, list[float]]:
    """librosa.beat_track -> (tempo_bpm, beat_grid_s)."""
    y, sr = librosa.load(str(wav_path), sr=22050)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    # librosa >=0.10 returns tempo as a 1-element ndarray, not a bare float.
    tempo_bpm = float(np.asarray(tempo).reshape(-1)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    return tempo_bpm, beat_times


def extract_sections(wav_path: Path) -> list[dict]:
    """Spectral-clustering segmentation -> [{t_in, t_out, label}, ...].

    Labels are GENERIC positional identifiers ("section_1", "section_2",
    ...), never semantic ("intro"/"drop") - semantic section labeling is
    L2's job (VLM, evidence-gated against these boundaries), not L1's. L1
    only measures that a boundary exists, not what it means.
    """
    y, sr = librosa.load(str(wav_path), sr=22050)
    duration_s = len(y) / sr
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)

    k = max(1, min(_SECTION_MAX_COUNT, round(duration_s / _SECTION_TARGET_LENGTH_S)))
    k = min(k, max(1, mfcc.shape[1] - 1))

    if k <= 1:
        return [{"t_in": 0.0, "t_out": duration_s, "label": "section_1"}]

    boundary_frames = librosa.segment.agglomerative(mfcc, k)
    boundary_times = sorted(set([0.0, *librosa.frames_to_time(boundary_frames, sr=sr).tolist(), duration_s]))

    return [
        {"t_in": boundary_times[i], "t_out": boundary_times[i + 1], "label": f"section_{i + 1}"}
        for i in range(len(boundary_times) - 1)
    ]


def transcribe(wav_path: Path) -> list[dict]:
    """faster-whisper with word timestamps -> [{t, word, conf}, ...].

    Model/device are CPU-friendly defaults (base, int8) - a GPU box should
    pass device="cuda", compute_type="float16" instead; this function
    always uses the CPU-friendly config since Phase 1 targets a CLI run
    with no GPU assumption. Model instantiation is NOT cached at module
    level - trace_builder.py (Unit 1.17) calls this once per video, and a
    per-call model would only matter for a hot loop, which this isn't.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav_path), word_timestamps=True)

    words: list[dict] = []
    for segment in segments:
        for word in segment.words or []:
            words.append({"t": float(word.start), "word": word.word.strip(), "conf": float(word.probability)})
    return words


def separate_speech_music(wav_path: Path) -> tuple[Path, Path]:
    """Demucs stem split -> (speech_stem_path, music_stem_path). Used so
    text.py's role classifier can tell captions (matches speech) from
    lyrics (matches music, not speech) apart.

    Real, somewhat slow step (seconds to low-minutes per video on CPU,
    per spec sec 8.5 - the model itself, not the shell-out, dominates).
    Requires the `audio-sep` optional dependency group (demucs) - not
    imported/required by any other function in this module.
    """
    import subprocess
    import sys

    out_dir = wav_path.parent / "demucs_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", str(out_dir), str(wav_path)],
        check=True, capture_output=True, text=True,
    )

    stem_dir = out_dir / "htdemucs" / wav_path.stem
    speech_stem_path = stem_dir / "vocals.wav"
    music_stem_path = stem_dir / "no_vocals.wav"
    return speech_stem_path, music_stem_path


def compute_beat_lock(cut_times_s: list[float], beat_grid_s: list[float]) -> tuple[float, int]:
    """Returns (beat_lock_ratio, median_cut_offset_frames) - see module
    docstring for why the offset must be signed and preserved, not
    normalized away."""
    raise NotImplementedError


def analyze_audio(wav_path: Path, cut_times_s: list[float]) -> AudioTrace:
    """Top-level entry point used by trace_builder.py."""
    raise NotImplementedError
