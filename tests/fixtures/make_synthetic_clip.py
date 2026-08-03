"""
Generates tests/fixtures/synthetic_clip.mp4 - a small, fully-synthetic,
license-free clip used by Phase 1 unit tests that need an actual decodable
video file (Unit 1.1's normalize/probe round-trip, in particular).

WHY THIS EXISTS (see DESIGN_NOTES.md / INSTRUCTIONS.md Unit 0.3): the real
20-30 video hand-annotated golden set required for the Unit 1.19 Phase 1
gate cannot be fabricated by an agent - it requires real short-form videos
the user has rights to use, hand-scrubbed for ground truth. Scraping
IG/TikTok in bulk is out of scope per spec sec 8.1/DESIGN_NOTES.md
"Legal posture". This generator instead produces a *synthetic* fixture with
exactly-known ground truth (baked in at generation time, not observed) so
that unit tests for individual detectors can run deterministically without
waiting on real footage. It is NOT a substitute for the golden set - do not
point eval/run.py's Phase-1-gate check at this file.

Ground truth baked into synthetic_clip.mp4 (see synthetic_clip.meta.json,
written alongside it):
  - 3 shots via 2 hard cuts at t=1.2s and t=2.0s (solid colors, hand-picked
    to have near-identical grayscale luminance ~130/255 despite being
    visually/HSV distinct - see signals/cuts.py's flash-vs-cut discriminator:
    naive primary colors like red/blue/green swing luminance by 100+, which
    reads as a false "flash" on a hard cut between two solid-color shots.
    Real footage's hard cuts rarely swing mean luminance this hard between
    similarly-exposed shots, so matching luminance here makes the fixture
    representative instead of adversarial)
  - one on-screen text layer "HOOK TEXT", visible t_in=0.2s, t_out=1.15s
    (drawtext on the red shot only)
  - a click-track audio at 120 BPM (beat every 0.5s) for the full 3.5s
    duration, so beat-grid extraction has a known-correct tempo/grid to
    check against
  - normalize_fps default (30), 1080x1920, CFR from birth (this fixture
    does NOT exercise the VFR code path - see the TODO below)

Run: python tests/fixtures/make_synthetic_clip.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
OUT_PATH = FIXTURE_DIR / "synthetic_clip.mp4"
META_PATH = FIXTURE_DIR / "synthetic_clip.meta.json"

# drawtext needs an explicit font file on this dev box - fontconfig isn't
# configured in this ffmpeg build (no fonts.conf found), so let libfreetype
# load the file directly instead of going through fontconfig lookup.
FONT_FILE = r"C:\Windows\Fonts\arial.ttf".replace("\\", "/").replace(":", "\\:")

FPS = 30
W, H = 1080, 1920

# (color, duration_s) - hex colors chosen so all three have ~equal grayscale
# luminance (~130/255, see module docstring), avoiding a false flash-vs-cut
# false positive from a big luminance swing between solid-color shots.
SHOTS = [("0xC86465", 1.2), ("0x14C83A", 0.8), ("0xCA50C8", 1.5)]
TOTAL_S = sum(d for _, d in SHOTS)
CUTS_S = [1.2, 2.0]  # cumulative boundaries between shots

TEXT_STRING = "HOOK TEXT"
TEXT_T_IN, TEXT_T_OUT = 0.2, 1.15  # within the first (red) shot

BEAT_INTERVAL_S = 0.5  # 120 BPM
BEAT_GRID_S = [round(i * BEAT_INTERVAL_S, 3) for i in range(int(TOTAL_S / BEAT_INTERVAL_S) + 1)]


def build() -> None:
    # One lavfi color source per shot, concatenated. drawtext is applied only
    # to the first segment's filter chain before concat.
    filter_parts = []
    concat_inputs = []
    for i, (color, dur) in enumerate(SHOTS):
        label = f"v{i}"
        if i == 0:
            filter_parts.append(
                f"color=c={color}:s={W}x{H}:d={dur}:r={FPS}[base{i}];"
                f"[base{i}]drawtext=fontfile='{FONT_FILE}':text='{TEXT_STRING}':"
                f"fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2:"
                f"enable='between(t,{TEXT_T_IN},{TEXT_T_OUT})'[{label}]"
            )
        else:
            filter_parts.append(f"color=c={color}:s={W}x{H}:d={dur}:r={FPS}[{label}]")
        concat_inputs.append(f"[{label}]")

    video_filter = ";".join(filter_parts)
    video_filter += f";{''.join(concat_inputs)}concat=n={len(SHOTS)}:v=1:a=0[outv]"

    # Click track: short sine burst every BEAT_INTERVAL_S seconds, full duration.
    audio_filter = (
        f"sine=frequency=1000:duration={TOTAL_S}:sample_rate=22050,"
        f"volume='if(lt(mod(t,{BEAT_INTERVAL_S}),0.03),1,0)':eval=frame[outa]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-filter_complex", f"{video_filter};{audio_filter}",
        "-map", "[outv]", "-map", "[outa]",
        "-vsync", "cfr", "-r", str(FPS), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-crf", "18",
        "-c:a", "aac", "-b:a", "96k",
        "-t", str(TOTAL_S),
        str(OUT_PATH),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    meta = {
        "duration_s": TOTAL_S,
        "fps": FPS,
        "w": W,
        "h": H,
        "cuts_s": CUTS_S,
        "shot_colors": [c for c, _ in SHOTS],
        "text_layers": [
            {"string": TEXT_STRING, "t_in": TEXT_T_IN, "t_out": TEXT_T_OUT}
        ],
        "beat_grid_s": BEAT_GRID_S,
        "tempo_bpm": 60.0 / BEAT_INTERVAL_S,
    }
    META_PATH.write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    build()
    print(f"wrote {OUT_PATH} and {META_PATH}")
