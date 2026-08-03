"""
L0 - mandatory CFR normalization. See RECUT_SPEC.md sec 2.2 - this step is
not optional and not a "nice to have"; every downstream timestamp (cuts,
beats, OCR windows) is measured against the normalized video's frame index,
and skipping this step silently corrupts beat-lock analysis on VFR sources
(most phone-captured short-form video is VFR).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ingest.probe import ProbeResult, probe_media


@dataclass
class NormalizeResult:
    normalized_path: Path
    wav_path: Path
    original_to_normalized_time_map: list[tuple[float, float]]
    fps: int
    width: int
    height: int
    was_vfr: bool


def probe(path: Path) -> dict:
    """Thin wrapper around ffprobe. Returns duration, fps, VFR flag,
    rotation matrix, audio stream info as a plain dict (this is intermediate
    plumbing, not a versioned schema - do not promote it into schemas/)."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def _linspace(start: float, stop: float, n: int) -> list[float]:
    if n < 2:
        return [start]
    step = (stop - start) / (n - 1)
    return [start + i * step for i in range(n)]


def _build_time_map(src: Path, src_probe: ProbeResult, fps: int) -> list[tuple[float, float]]:
    """Identity map (sparse, 1 point/sec) for already-CFR sources. For VFR
    sources, pairs the original per-frame presentation timestamps against
    the normalized (now-CFR) output's frame index, per spec sec 2.2 - this
    is what lets a user-facing timestamp be translated back to the original
    upload if ever needed for debugging."""
    if not src_probe.is_vfr:
        n_points = max(2, int(src_probe.duration_s) + 1)
        return [(round(t, 3), round(t, 3)) for t in _linspace(0.0, src_probe.duration_s, n_points)]

    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-select_streams", "v:0",
            "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(src),
        ],
        check=True, capture_output=True, text=True,
    )
    original_pts = [float(line) for line in result.stdout.splitlines() if line.strip()]
    normalized_pts = [round(i / fps, 6) for i in range(len(original_pts))]
    return list(zip(original_pts, normalized_pts))


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
    out_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = out_dir / "norm.mp4"
    wav_path = out_dir / "norm.wav"

    src_probe = probe_media(src)

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-vsync", "cfr", "-r", str(fps),
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            "-c:v", "libx264", "-crf", str(crf),
            "-c:a", "pcm_s16le",
            str(normalized_path),
        ],
        check=True, capture_output=True, text=True,
    )

    # Mono 22050Hz matches librosa.load's default sr - avoids a resample step
    # being silently repeated in every signals/audio.py call site.
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(normalized_path),
            "-ar", "22050", "-ac", "1",
            str(wav_path),
        ],
        check=True, capture_output=True, text=True,
    )

    time_map = _build_time_map(src, src_probe, fps)

    return NormalizeResult(
        normalized_path=normalized_path,
        wav_path=wav_path,
        original_to_normalized_time_map=time_map,
        fps=fps,
        width=width,
        height=height,
        was_vfr=src_probe.is_vfr,
    )
