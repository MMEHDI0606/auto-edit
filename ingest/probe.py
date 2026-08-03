"""
L0 - thin ffprobe wrapper used by normalize.py and by the matcher (L4) when
probing user-supplied assets. Kept separate from normalize.py so matcher/
can depend on ingest/probe.py without pulling in the yt-dlp/download path.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProbeResult:
    duration_s: float
    fps: float
    is_vfr: bool
    width: int
    height: int
    rotation_deg: int
    has_audio: bool


def _parse_rate(rate_str: str) -> float:
    """Parses ffprobe's "num/den" frame-rate strings (e.g. "30000/1001")."""
    if "/" in rate_str:
        num, den = rate_str.split("/", 1)
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    return float(rate_str)


def _extract_rotation(video_stream: dict) -> int:
    """Rotation can show up either as a legacy `tags.rotate` string or, on
    modern ffmpeg, as a `rotation` field inside `side_data_list` (Display
    Matrix). Check both; default to 0 (no rotation) if neither is present."""
    tags = video_stream.get("tags", {})
    if "rotate" in tags:
        return int(tags["rotate"])
    for side_data in video_stream.get("side_data_list", []):
        if "rotation" in side_data:
            # Display-matrix rotation is signed and can be e.g. -90; normalize
            # to the 0/90/180/270 convention the rest of the system expects.
            return int(side_data["rotation"]) % 360
    return 0


def _run_ffprobe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def probe_media(path: Path) -> ProbeResult:
    """Raises subprocess.CalledProcessError unmodified on ffprobe failure
    (fail loudly, per project-wide policy) and StopIteration-derived errors
    if the file has no video stream at all (also a real failure, not a
    condition to swallow)."""
    data = _run_ffprobe(path)
    video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio_streams = [s for s in data["streams"] if s["codec_type"] == "audio"]

    r_frame_rate = _parse_rate(video_stream["r_frame_rate"])
    avg_frame_rate = _parse_rate(video_stream.get("avg_frame_rate") or video_stream["r_frame_rate"])
    # VFR sources report a nominal r_frame_rate that diverges from the actual
    # average once real per-frame durations are accounted for - see spec sec 2.2.
    is_vfr = abs(r_frame_rate - avg_frame_rate) > 0.01

    duration_s = float(data["format"].get("duration") or video_stream.get("duration") or 0.0)

    return ProbeResult(
        duration_s=duration_s,
        fps=avg_frame_rate,
        is_vfr=is_vfr,
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        rotation_deg=_extract_rotation(video_stream),
        has_audio=len(audio_streams) > 0,
    )
