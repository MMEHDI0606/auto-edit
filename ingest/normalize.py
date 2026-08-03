"""
L0 - mandatory CFR normalization. See RECUT_SPEC.md sec 2.2 - this step is
not optional and not a "nice to have"; every downstream timestamp (cuts,
beats, OCR windows) is measured against the normalized video's frame index,
and skipping this step silently corrupts beat-lock analysis on VFR sources
(most phone-captured short-form video is VFR).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class NormalizeResult:
    normalized_path: Path
    wav_path: Path
    original_to_normalized_time_map: list[tuple[float, float]]
    fps: int
    width: int
    height: int
    was_vfr: bool


def normalize(src: Path, out_dir: Path, *, fps: int, width: int, height: int, crf: int) -> NormalizeResult:
    """Runs the ffmpeg pipeline from spec sec 2.2:

        ffmpeg -i in.mp4 -vsync cfr -r {fps} -pix_fmt yuv420p
               -vf "scale={width}:{height}:force_original_aspect_ratio=decrease"
               -c:v libx264 -crf {crf} -c:a pcm_s16le norm.mp4

    Must also extract a WAV (for librosa/whisper) and, when the source was
    VFR, persist an original<->normalized time map so any user-facing
    timestamp can be translated back if ever needed (e.g. debugging against
    the original uploaded file).

    Raises:
        subprocess.CalledProcessError: propagate ffmpeg failures unchanged;
        do not swallow them - a silent normalization failure is worse than
        a loud one, per the "fail loudly" principle applied project-wide.
    """
    raise NotImplementedError


def probe(path: Path) -> dict:
    """Thin wrapper around ffprobe. Returns duration, fps, VFR flag,
    rotation matrix, audio stream info as a plain dict (this is intermediate
    plumbing, not a versioned schema - do not promote it into schemas/).
    """
    raise NotImplementedError
