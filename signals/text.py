"""
L1 - on-screen text detection, temporal grouping into layers, and style
extraction. See RECUT_SPEC.md sec 3.3.

Pipeline:
  1. Sample frames at Settings.ocr_sample_fps (default 8 - NOT 1fps; text
     can flash for <500ms and 1fps will simply miss it).
  2. PaddleOCR/EasyOCR per sampled frame -> boxes + text + confidence.
  3. Temporal grouping: cluster boxes across frames by
     (normalized bbox IoU, string similarity >= 0.8) into text layers with
     t_in/t_out. This is the trickiest part of this module - two distinct
     on-screen strings that happen to occupy the same box in sequence must
     NOT merge into one layer; tune the similarity threshold against the
     golden set, don't hand-guess it.
  4. Per layer: position/size, fill/stroke color (sample inside/outside the
     glyph mask), background pill presence, entrance/exit animation
     classification over the first/last 8 frames, font nearest-neighbor
     match against the curated font library (see font_match below).
  5. Role classification (hook_title / caption_burnin / lyric / label / cta
     / watermark) - caption_burnin vs lyric is resolved by cross-matching
     against the Whisper transcript vs the music track (see spec sec 8.3,
     "burned-in captions vs speech" mitigation) - this module must accept
     the transcript as an input, it cannot resolve that ambiguity alone.

IMPORTANT (see mcp/tools.py and DESIGN_NOTES.md "untrusted OCR text"):
every string returned here is UNTRUSTED INPUT (extracted from third-party
video). This module's job is extraction, not sanitization - it must not
attempt to interpret/execute anything in the string. Downstream consumers
(L2 prompts, MCP tool responses) are responsible for wrapping/labeling it.
"""

from __future__ import annotations

import difflib
from itertools import groupby
from pathlib import Path

import cv2

from schemas.models import TextLayer

_GRACE_WINDOW_MISSED_FRAMES = 1  # tolerate exactly 1 missed sampled frame before closing a layer


def sample_and_ocr(normalized_video_path: Path, *, sample_fps: int) -> list[dict]:
    """Returns raw per-frame OCR boxes: [{t, text, box, conf}, ...]. Boxes
    are normalized to [0,1] relative to the frame's own width/height, so
    downstream comparisons are resolution-independent (spec sec 3.3).

    Requires the `ocr` optional dependency group (PaddleOCR) - imported
    lazily here rather than at module level so importing signals.text for
    group_into_layers()/classify_role() etc doesn't force a PaddleOCR
    install on anyone not running the OCR step.
    """
    from paddleocr import PaddleOCR

    cap = cv2.VideoCapture(str(normalized_video_path))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    frame_stride = max(1, round(video_fps / sample_fps))
    ocr = PaddleOCR(use_angle_cls=True, lang="en")

    raw_boxes: list[dict] = []
    frame_idx = 0
    while frame_idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            break
        t = frame_idx / video_fps
        result = ocr.ocr(frame, cls=True)
        for line in result or []:
            for detection in line or []:
                quad, (text, conf) = detection
                xs = [p[0] for p in quad]
                ys = [p[1] for p in quad]
                x, y = min(xs), min(ys)
                w, h = max(xs) - x, max(ys) - y
                raw_boxes.append({
                    "t": t,
                    "text": text,
                    "box": (x / frame_w, y / frame_h, w / frame_w, h / frame_h),
                    "conf": float(conf),
                })
        frame_idx += frame_stride

    cap.release()
    return raw_boxes


def _iou(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    inter_x1, inter_y1 = max(ax, bx), max(ay, by)
    inter_x2, inter_y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter_w, inter_h = max(0.0, inter_x2 - inter_x1), max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    union_area = aw * ah + bw * bh - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def _string_sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def group_into_layers(
    raw_boxes: list[dict], *, iou_threshold: float = 0.5, string_sim_threshold: float = 0.8
) -> list[dict]:
    """Temporal clustering of raw per-frame boxes into candidate layers
    (pre-style-extraction). Kept separate from sample_and_ocr so it can be
    unit tested against synthetic box sequences without running real OCR.

    Greedy walk in time order: a box extends an open layer if it matches on
    BOTH normalized-bbox IoU and string similarity; matches on IoU alone
    (same position, different text) closes the old layer and opens a new
    one at that position - two distinct strings in the same box must not
    merge. A layer not matched in the current sampled frame gets one grace
    frame (tolerates a single missed OCR detection) before closing.

    NOTE: a sampled frame with literally zero detections anywhere never
    appears as a distinct step here (there is nothing in raw_boxes to mark
    it) - the grace window only fires for a miss that happens on a
    timestamp where >=1 other box was detected. This is an inherent limit
    of taking a flat detection list with no separate "frames sampled" grid
    as input, matching this function's given signature.
    """
    boxes_sorted = sorted(raw_boxes, key=lambda b: b["t"])

    open_layers: list[dict] = []
    closed_layers: list[dict] = []

    for t, group in groupby(boxes_sorted, key=lambda b: b["t"]):
        frame_boxes = list(group)
        matched_ids: set[int] = set()

        for fb in frame_boxes:
            best_layer, best_iou = None, 0.0
            for layer in open_layers:
                if id(layer) in matched_ids:
                    continue  # don't double-match one open layer within the same frame
                iou = _iou(layer["box"], fb["box"])
                if iou >= iou_threshold and iou > best_iou:
                    best_layer, best_iou = layer, iou

            if best_layer is not None and _string_sim(best_layer["string"], fb["text"]) >= string_sim_threshold:
                best_layer["t_out"] = t
                best_layer["box"] = fb["box"]
                best_layer["missed_frames"] = 0
                matched_ids.add(id(best_layer))
                continue

            if best_layer is not None:
                # Same position, different string - close the old layer,
                # open a fresh one; do NOT merge them.
                closed_layers.append(best_layer)
                open_layers.remove(best_layer)

            new_layer = {"t_in": t, "t_out": t, "string": fb["text"], "box": fb["box"], "missed_frames": 0}
            open_layers.append(new_layer)
            matched_ids.add(id(new_layer))

        still_open = []
        for layer in open_layers:
            if id(layer) in matched_ids:
                still_open.append(layer)
                continue
            layer["missed_frames"] += 1
            if layer["missed_frames"] > _GRACE_WINDOW_MISSED_FRAMES:
                closed_layers.append(layer)
            else:
                still_open.append(layer)
        open_layers = still_open

    closed_layers.extend(open_layers)
    closed_layers.sort(key=lambda l: l["t_in"])
    return [
        {"t_in": l["t_in"], "t_out": l["t_out"], "string": l["string"], "box": l["box"]}
        for l in closed_layers
    ]


def classify_entrance_exit(layer_frames: list) -> tuple[str, str, int]:
    """Returns (in_animation, out_animation, in_duration_f) by tracking
    bbox + alpha over the first/last 8 frames of the layer."""
    raise NotImplementedError


def font_match(glyph_crop, *, font_library_dir: Path) -> tuple[str, float]:
    """Renders candidate fonts from the curated library and compares glyph
    raster to the crop; returns (best_guess, confidence). This is
    approximate by design (spec sec 8.6) - callers should always be able to
    surface top-3 candidates for user override, so consider returning a
    ranked list here rather than just the top-1 once this is implemented.
    """
    raise NotImplementedError


def classify_role(layer: dict, *, transcript_words: list[dict], music_active: bool) -> tuple[str, float]:
    """caption_burnin vs lyric vs hook_title/label/cta/watermark - see
    module docstring. Requires transcript_words (faster-whisper output,
    from audio.py) and a music-active signal to disambiguate speech vs song."""
    raise NotImplementedError


def extract_text_layers(normalized_video_path: Path, *, transcript_words: list[dict]) -> list[TextLayer]:
    """Top-level entry point used by trace_builder.py."""
    raise NotImplementedError
