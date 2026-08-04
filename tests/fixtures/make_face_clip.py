"""
Generates tests/fixtures/synthetic_face_clip.mp4 - a real-face-containing
test clip for matcher/probe.py's face-detection path (Unit 3.6), paired
with tests/fixtures/synthetic_speech.wav (existing, real Windows-SAPI TTS
audio) for the has_speech path.

WHY A REAL FACE IMAGE, NOT A DRAWN ONE (see DESIGN_NOTES.md's stance on
synthetic-but-real fixtures elsewhere in this test suite): a Haar cascade
detects actual facial feature geometry (eyes/nose/mouth arrangement) - a
drawn shape (circle + dots) will not reliably trigger it, so a fabricated
"face" would be worse than no test at all (asserting behavior against an
input that doesn't exercise the real detection path). scikit-image ships
`skimage.data.astronaut()` - a public-domain NASA photo (Eileen Collins)
bundled specifically for CV testing/demos exactly like this - already an
installed dependency (transitively, via other packages), not a new fetch.

This is NOT a substitute for the real "5-10 varied local test clips"
Unit 3.6's own done criteria asks for (with/without faces, different
orientations, with/without speech) - that variety needs real donated
footage, blocked the same way as the golden-set video (see
eval/golden/NEEDS_INPUT.md). This fixture covers the has_face=True /
has_speech=True branches specifically; the existing synthetic_clip.mp4
(solid colors, click-track audio) covers has_face=False / has_speech=False.

Run: python tests/fixtures/make_face_clip.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import skimage.data

FIXTURE_DIR = Path(__file__).parent
SILENT_VIDEO_PATH = FIXTURE_DIR / "_synthetic_face_clip_silent.mp4"
OUT_PATH = FIXTURE_DIR / "synthetic_face_clip.mp4"
SPEECH_WAV_PATH = FIXTURE_DIR / "synthetic_speech.wav"

FPS = 30
DURATION_S = 5.19  # matches synthetic_speech.wav's real duration (114411 samples / 22050Hz)


def build() -> None:
    frame_bgr = cv2.cvtColor(skimage.data.astronaut(), cv2.COLOR_RGB2BGR)
    height, width = frame_bgr.shape[:2]

    writer = cv2.VideoWriter(str(SILENT_VIDEO_PATH), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (width, height))
    for _ in range(round(DURATION_S * FPS)):
        writer.write(frame_bgr)
    writer.release()

    # Mux in the existing real speech audio - re-encode video to h264 in the
    # same pass since mp4v (from cv2.VideoWriter) isn't a great delivery
    # codec and ffmpeg is already in the loop for the audio mux anyway.
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(SILENT_VIDEO_PATH),
            "-i", str(SPEECH_WAV_PATH),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(OUT_PATH),
        ],
        check=True, capture_output=True, text=True,
    )
    SILENT_VIDEO_PATH.unlink()


if __name__ == "__main__":
    build()
    print(f"wrote {OUT_PATH}")
