"""
L0 - thin ffprobe wrapper used by normalize.py and by the matcher (L4) when
probing user-supplied assets. Kept separate from normalize.py so matcher/
can depend on ingest/probe.py without pulling in the yt-dlp/download path.
"""

from __future__ import annotations

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


def probe_media(path: Path) -> ProbeResult:
    raise NotImplementedError
