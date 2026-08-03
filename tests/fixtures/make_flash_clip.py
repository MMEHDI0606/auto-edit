"""
Generates tests/fixtures/synthetic_flash_clip.mp4 for Unit 1.5's
transition-classification tests: two solid-color shots (red, blue)
separated by a few pure-white flash frames at the boundary - a real,
decodable video exercising the FLASH branch of signals.cuts._classify_boundary,
distinct from tests/fixtures/synthetic_clip.mp4 (hard cuts only, no flash).

Run: python tests/fixtures/make_flash_clip.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
OUT_PATH = FIXTURE_DIR / "synthetic_flash_clip.mp4"
META_PATH = FIXTURE_DIR / "synthetic_flash_clip.meta.json"

FPS = 30
W, H = 640, 1138  # smaller than synthetic_clip.mp4 - keeps flow/hist computation fast in tests
RED_S = 1.0
FLASH_S = 4 / FPS  # 4 frames of pure white
BLUE_S = 1.0
TOTAL_S = RED_S + FLASH_S + BLUE_S


def build() -> None:
    filter_complex = (
        f"color=c=red:s={W}x{H}:d={RED_S}:r={FPS}[v0];"
        f"color=c=white:s={W}x{H}:d={FLASH_S}:r={FPS}[v1];"
        f"color=c=blue:s={W}x{H}:d={BLUE_S}:r={FPS}[v2];"
        f"[v0][v1][v2]concat=n=3:v=1:a=0[outv]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-vsync", "cfr", "-r", str(FPS), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-crf", "18",
        "-t", str(TOTAL_S),
        str(OUT_PATH),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    meta = {
        "duration_s": TOTAL_S,
        "fps": FPS,
        "w": W,
        "h": H,
        "flash_boundary_s": RED_S,  # first boundary (red -> white) is the flash
        "second_boundary_s": RED_S + FLASH_S,  # white -> blue
    }
    META_PATH.write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    build()
    print(f"wrote {OUT_PATH} and {META_PATH}")
