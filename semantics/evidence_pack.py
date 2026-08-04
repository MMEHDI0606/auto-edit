"""
L2 - builds the compact "evidence pack" handed to a VLM provider. See
RECUT_SPEC.md sec 4.1.

Never stream the whole video into a model at high FPS - build:
  - a contact sheet per shot (first/middle/last frame, tiled, burned-in
    timestamps)
  - the numeric EditTrace (already small)
  - OCR strings + transcript + beat grid

Contact sheets are cached alongside the trace (keyed by content hash + shot
id) so re-running the semantics layer (e.g. after a model upgrade) doesn't
re-render them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from schemas.models import EditTrace

_TRIAGE_SAMPLE_INTERVAL_S = 1.0  # whole-video sheet: one frame per this many seconds, sec 4.2
_TRIAGE_GRID_MAX_COLS = 10
_TIMESTAMP_MARGIN_PX = 12
_TIMESTAMP_FONT_SIZE = 48  # PIL's bitmap default font is ~11px - illegible against a 1080px-wide frame


def _timestamp_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Best-effort: a real scalable font makes contact sheets actually
    # reviewable by eye (the done criterion); falls back to PIL's tiny
    # bitmap default only on a box with no system fonts at all.
    for candidate in (r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, _TIMESTAMP_FONT_SIZE)
    return ImageFont.load_default()


@dataclass
class ContactSheet:
    shot_id: str
    image_path: Path  # tiled first/middle/last frame, timestamps burned in


@dataclass
class EvidencePack:
    trace: EditTrace
    contact_sheets: list[ContactSheet]
    whole_video_low_res_sheet: Path  # for the triage pass, sec 4.2


def _read_frame_at(cap: cv2.VideoCapture, t_s: float, fps: float) -> np.ndarray:
    frame_idx = max(0, round(t_s * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame_bgr = cap.read()
    if not ok:
        # t exactly at/past EOF (e.g. a shot's t_out landing on the final
        # frame boundary) - fall back one frame rather than failing the
        # whole contact sheet over an off-by-one.
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx - 1))
        ok, frame_bgr = cap.read()
        if not ok:
            raise ValueError(f"could not read a frame near t={t_s:.3f}s (frame {frame_idx})")
    return frame_bgr


def _burn_in_timestamp(frame_bgr: np.ndarray, t_s: float) -> Image.Image:
    """Burns `{t:.2f}s` into the top-left corner - white-on-black-outline
    so it stays legible over arbitrary frame content, matching against the
    same t_in/t_out the trace records (this IS the evidence trail: a human
    reviewing a contact sheet must be able to check the burned-in time
    against Shot.t_in/t_out directly)."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(img)
    label = f"{t_s:.2f}s"
    font = _timestamp_font()
    pos = (_TIMESTAMP_MARGIN_PX, _TIMESTAMP_MARGIN_PX)
    for dx, dy in ((-2, -2), (-2, 2), (2, -2), (2, 2)):
        draw.text((pos[0] + dx, pos[1] + dy), label, font=font, fill="black")
    draw.text(pos, label, font=font, fill="white")
    return img


def _tile_horizontal(images: list[Image.Image]) -> Image.Image:
    height = max(img.height for img in images)
    resized = [
        img if img.height == height else img.resize((round(img.width * height / img.height), height))
        for img in images
    ]
    sheet = Image.new("RGB", (sum(img.width for img in resized), height))
    x = 0
    for img in resized:
        sheet.paste(img, (x, 0))
        x += img.width
    return sheet


def _tile_grid(images: list[Image.Image], *, max_cols: int) -> Image.Image:
    cols = min(max_cols, len(images))
    rows = math.ceil(len(images) / cols)
    cell_w = max(img.width for img in images)
    cell_h = max(img.height for img in images)
    sheet = Image.new("RGB", (cell_w * cols, cell_h * rows), color="black")
    for i, img in enumerate(images):
        r, c = divmod(i, cols)
        sheet.paste(img, (c * cell_w, r * cell_h))
    return sheet


def _sample_times(duration_s: float, interval_s: float) -> list[float]:
    n = max(1, math.floor(duration_s / interval_s) + 1)
    return [round(i * interval_s, 3) for i in range(n)]


def build_evidence_pack(trace: EditTrace, normalized_video_path: Path, *, cache_dir: Path) -> EvidencePack:
    hash_dir = cache_dir / trace.source.hash
    contact_sheets_dir = hash_dir / "contact_sheets"
    contact_sheets_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(normalized_video_path))
    if not cap.isOpened():
        raise ValueError(f"could not open {normalized_video_path}")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or trace.source.fps

        contact_sheets: list[ContactSheet] = []
        for shot in trace.shots:
            image_path = contact_sheets_dir / f"{shot.id}.png"
            if not image_path.exists():
                midpoint = (shot.t_in + shot.t_out) / 2
                tiles = [_burn_in_timestamp(_read_frame_at(cap, t, fps), t) for t in (shot.t_in, midpoint, shot.t_out)]
                _tile_horizontal(tiles).save(image_path)
            contact_sheets.append(ContactSheet(shot_id=shot.id, image_path=image_path))

        whole_video_path = hash_dir / "whole_video_sheet.png"
        if not whole_video_path.exists():
            times = _sample_times(trace.source.duration_s, _TRIAGE_SAMPLE_INTERVAL_S)
            frames = [_burn_in_timestamp(_read_frame_at(cap, t, fps), t) for t in times]
            _tile_grid(frames, max_cols=_TRIAGE_GRID_MAX_COLS).save(whole_video_path)
    finally:
        cap.release()

    return EvidencePack(trace=trace, contact_sheets=contact_sheets, whole_video_low_res_sheet=whole_video_path)
