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
from collections import Counter
from itertools import groupby
from pathlib import Path

import cv2
import numpy as np

from schemas.models import TextAnimation, TextLayer, TextStyle

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


def bbox_iou(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
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
                iou = bbox_iou(layer["box"], fb["box"])
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


def _bbox_area(box: tuple[float, float, float, float]) -> float:
    return box[2] * box[3]


def _classify_direction(frames: list[dict]) -> tuple[str, float]:
    """Classifies one END (entrance as given, exit pass reversed so it
    reads the same "growing in" way) from a chronological list of
    {"box": (x,y,w,h), "alpha": float} samples. Defaults to `fade` at low
    confidence when no signal is clear, per INSTRUCTIONS.md Unit 1.8 -
    never force a specific guess the frames don't support."""
    if len(frames) < 2:
        return TextAnimation.fade.value, 0.3

    areas = np.array([_bbox_area(f["box"]) for f in frames], dtype=np.float64)
    xs = np.array([f["box"][0] for f in frames], dtype=np.float64)
    ys = np.array([f["box"][1] for f in frames], dtype=np.float64)
    alphas = np.array([f.get("alpha", 1.0) for f in frames], dtype=np.float64)

    area0 = areas[0] if areas[0] > 1e-9 else 1e-9
    early_idx = min(2, len(areas) - 1)
    growth = areas[early_idx] / area0
    late_areas = areas[early_idx:]
    size_stable_after_growth = (
        float(np.std(late_areas)) / (float(np.mean(late_areas)) + 1e-9) < 0.1 if len(late_areas) else True
    )
    if growth > 1.2 and size_stable_after_growth:
        return TextAnimation.pop.value, min(1.0, growth - 1.0)

    x_mean = float(np.mean(xs)) or 1e-9
    x_stable = float(np.std(xs)) / abs(x_mean) < 0.1
    area_mean = float(np.mean(areas)) or 1e-9
    size_stable = float(np.std(areas)) / abs(area_mean) < 0.15

    y_diffs = np.diff(ys)
    if len(y_diffs) and np.all(y_diffs <= 1e-6) and x_stable and size_stable and abs(ys[0] - ys[-1]) > 0.02:
        return TextAnimation.slide_up.value, 0.8

    if len(y_diffs) > 1:
        signs = np.sign(y_diffs)
        signs = signs[signs != 0]
        sign_changes = int(np.sum(np.diff(signs) != 0)) if len(signs) > 1 else 0
        if sign_changes >= 2:
            return TextAnimation.bounce.value, 0.6

    alpha_delta = float(alphas[-1] - alphas[0])
    if len(alphas) and np.all(np.diff(alphas) >= -1e-6) and alpha_delta > 0.2 and x_stable and size_stable:
        return TextAnimation.fade.value, 0.8

    return TextAnimation.fade.value, 0.3


def classify_entrance_exit(layer_frames: list[dict]) -> tuple[str, str, int]:
    """Returns (in_animation, out_animation, in_duration_f) by tracking
    bbox + alpha over the first/last 8 frames of the layer.

    `layer_frames` is the chronological per-sampled-frame track for this
    ONE layer's whole lifetime: [{"box": (x,y,w,h), "alpha": float}, ...]
    (alpha optional, approximated by the caller e.g. via edge density or
    background-subtraction - see module docstring point 4). typewriter/
    word_by_word (string-length-over-time signals) aren't resolvable from
    box+alpha alone at 8fps sampling and are intentionally NOT attempted
    here - per INSTRUCTIONS.md Unit 1.8, best-effort/low-confidence only,
    and this function has no string-length-per-frame input to work with.
    """
    if not layer_frames:
        return TextAnimation.fade.value, TextAnimation.fade.value, 0

    window = min(8, len(layer_frames))
    entrance = layer_frames[:window]
    exit_reversed = list(reversed(layer_frames[-window:]))

    in_animation, _in_conf = _classify_direction(entrance)
    out_animation, _out_conf = _classify_direction(exit_reversed)

    return in_animation, out_animation, len(entrance)


def _mode_color(pixels: np.ndarray) -> tuple[int, int, int]:
    """True mode (most frequent exact BGR triple), per INSTRUCTIONS.md
    Unit 1.8 ("sample the mode... color") - not mean/median, which would
    blend anti-aliased edge pixels into a color that never actually
    appears in the glyph."""
    tuples = [tuple(int(c) for c in p) for p in pixels]
    most_common, _count = Counter(tuples).most_common(1)[0]
    return most_common


def _bgr_to_hex(bgr: tuple[int, int, int]) -> str:
    b, g, r = bgr
    return f"#{r:02X}{g:02X}{b:02X}"


_PILL_MAX_INNER_MAD = 12.0
_PILL_MIN_COLOR_DELTA = 20.0


def _detect_background_pill(frame: np.ndarray, box_px: tuple[int, int, int, int], glyph_mask: np.ndarray) -> bool:
    """A background pill/highlight box reads as: the background BEHIND the
    text (i.e. the bbox with glyph pixels excluded, via glyph_mask) is
    fairly uniform in color AND a genuinely different color from the
    general surrounding background.

    Excluding glyph pixels is essential, not cosmetic: the raw bbox crop
    always has high variance (background + bright glyph strokes) whether
    or not a pill exists, so measuring variance over the whole crop can't
    distinguish "plain background with text on it" from "a pill" - only
    the non-glyph portion carries that signal.

    Uses MEDIAN + median-absolute-deviation, not mean/std: anti-aliased
    glyph-edge pixels leak past the Otsu mask as a small minority of
    background-labeled pixels with intermediate brightness, which is
    enough to blow up plain std/mean on an otherwise near-uniform pill
    color. MAD is robust to that minority the way std isn't (verified
    empirically: a solid-color pill with anti-aliased 4px text on it had
    std ~90 but MAD ~0 on the same non-glyph pixels)."""
    x, y, w, h = box_px
    fh, fw = frame.shape[:2]

    crop = frame[y : y + h, x : x + w]
    inner_pixels = crop[glyph_mask == 0] if glyph_mask.shape[:2] == crop.shape[:2] else crop.reshape(-1, 3)
    if len(inner_pixels) == 0:
        return False
    inner_median = np.median(inner_pixels, axis=0)
    inner_mad = float(np.median(np.abs(inner_pixels.astype(np.float32) - inner_median)))

    outer_pad = max(w, h, 1)
    ox, oy = max(0, x - outer_pad), max(0, y - outer_pad)
    ow, oh = min(fw, x + w + outer_pad) - ox, min(fh, y + h + outer_pad) - oy
    outer_region = frame[oy : oy + oh, ox : ox + ow]

    mask = np.ones(outer_region.shape[:2], dtype=bool)
    rel_x, rel_y = x - ox, y - oy
    mask[rel_y : rel_y + h, rel_x : rel_x + w] = False
    outer_pixels = outer_region[mask]
    if len(outer_pixels) == 0:
        return False
    outer_median = np.median(outer_pixels, axis=0)

    color_delta = float(np.linalg.norm(inner_median - outer_median))
    return inner_mad < _PILL_MAX_INNER_MAD and color_delta > _PILL_MIN_COLOR_DELTA


def extract_text_style(frame: np.ndarray, box: tuple[float, float, float, float]) -> TextStyle:
    """Style-extraction portion of extract_text_layers() (INSTRUCTIONS.md
    Unit 1.8): position/size, fill/stroke color, background-pill presence.
    `box` is normalized [0,1] (x, y, w, h), matching group_into_layers()'s
    output. font_guess/font_confidence are left at their schema defaults -
    that's font_match(), Unit 1.8b, explicitly deferred.

    Caller passes the frame at the layer's temporal midpoint (per spec
    sec 3.3 point 4) - this function itself is frame-agnostic.
    """
    fh, fw = frame.shape[:2]
    x_norm, y_norm, w_norm, h_norm = box
    x, y = max(0, int(x_norm * fw)), max(0, int(y_norm * fh))
    w = min(fw - x, max(1, int(w_norm * fw)))
    h = min(fh - y, max(1, int(h_norm * fh)))

    crop = frame[y : y + h, x : x + w]
    if crop.size == 0:
        return TextStyle(size_rel=h_norm)

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _thresh_val, glyph_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu splits into two clusters but doesn't know which is "the glyph" -
    # glyph strokes are almost always the minority of pixels in a text crop,
    # so if the mask covers the majority, it picked the background; invert.
    if float(np.mean(glyph_mask)) > 127:
        glyph_mask = 255 - glyph_mask

    glyph_pixels = crop[glyph_mask > 0]
    fill_bgr = _mode_color(glyph_pixels) if len(glyph_pixels) else (255, 255, 255)

    dilated = cv2.dilate(glyph_mask, np.ones((3, 3), np.uint8), iterations=2)
    ring_mask = cv2.bitwise_and(dilated, cv2.bitwise_not(glyph_mask))
    ring_pixels = crop[ring_mask > 0]
    if len(ring_pixels):
        stroke_bgr: tuple[int, int, int] | None = _mode_color(ring_pixels)
        stroke_px = 2.0  # approximate: matches the dilation width sampled above
    else:
        stroke_bgr, stroke_px = None, 0.0

    return TextStyle(
        fill=_bgr_to_hex(fill_bgr),
        stroke=_bgr_to_hex(stroke_bgr) if stroke_bgr is not None else None,
        stroke_px=stroke_px,
        size_rel=h_norm,
        has_background_pill=_detect_background_pill(frame, (x, y, w, h), glyph_mask),
    )


def font_match(glyph_crop, *, font_library_dir: Path) -> tuple[str, float]:
    """Renders candidate fonts from the curated library and compares glyph
    raster to the crop; returns (best_guess, confidence). This is
    approximate by design (spec sec 8.6) - callers should always be able to
    surface top-3 candidates for user override, so consider returning a
    ranked list here rather than just the top-1 once this is implemented.
    """
    raise NotImplementedError


_CAPTION_TRANSCRIPT_SIM_THRESHOLD = 0.6
_WATERMARK_CORNER_FRACTION = 0.15
_WATERMARK_PERSISTENCE_FRACTION = 0.9
_HOOK_TITLE_EARLY_FRACTION = 0.2
_CTA_LATE_FRACTION = 0.85
_CTA_MAX_WORDS = 3


def classify_role(
    layer: dict,
    *,
    transcript_words: list[dict],
    music_active: bool,
    video_duration_s: float | None = None,
    median_size_rel: float | None = None,
) -> tuple[str, float]:
    """caption_burnin vs lyric vs hook_title/label/cta/watermark - see
    module docstring. Requires transcript_words (faster-whisper output,
    from audio.py) and a music-active signal to disambiguate speech vs song.

    Decision order matters (first match wins), per INSTRUCTIONS.md Unit 1.11:
      1. watermark   - bottom/corner position, persists near the whole clip
      2. caption_burnin - OCR string matches OVERLAPPING transcript words
         (speech_active, derived here from "any transcript word falls in
         this layer's time window" - there's no separate speech-stem-RMS
         input to this function) AND that similarity is high
      3. lyric       - music is active and speech is NOT (no overlapping
         transcript words) - this is the concrete guard against the spec
         sec 8.3 "burned-in captions vs speech" confusion
      4. hook_title  - early in the clip AND prominently sized
      5. cta         - short string, near the end (best-effort heuristic)
      6. label       - default

    Signature extended beyond the stub with `video_duration_s` and
    `median_size_rel` (both needed for the hook_title/cta checks the
    module docstring itself describes) - no caller existed yet to break.
    """
    t_in, t_out = layer["t_in"], layer["t_out"]
    box = layer.get("box")
    string = layer.get("string", "")

    if box is not None and video_duration_s:
        x, y, w, h = box
        in_corner = (x < _WATERMARK_CORNER_FRACTION or x + w > 1 - _WATERMARK_CORNER_FRACTION) and (
            y + h > 1 - _WATERMARK_CORNER_FRACTION
        )
        persists = (t_out - t_in) >= _WATERMARK_PERSISTENCE_FRACTION * video_duration_s
        if in_corner and persists:
            return "watermark", 0.9

    overlapping_words = [w for w in transcript_words if t_in <= w["t"] <= t_out]
    speech_active = len(overlapping_words) > 0
    overlapping_text = " ".join(w["word"] for w in overlapping_words)
    ocr_transcript_sim = (
        difflib.SequenceMatcher(None, string.lower(), overlapping_text.lower()).ratio() if overlapping_text else 0.0
    )

    if ocr_transcript_sim >= _CAPTION_TRANSCRIPT_SIM_THRESHOLD and speech_active:
        return "caption_burnin", min(1.0, 0.5 + ocr_transcript_sim / 2)

    if music_active and not speech_active:
        return "lyric", 0.7

    if box is not None and video_duration_s and median_size_rel is not None:
        is_early = t_in <= _HOOK_TITLE_EARLY_FRACTION * video_duration_s
        is_prominent = box[3] >= median_size_rel
        if is_early and is_prominent:
            return "hook_title", 0.7

    word_count = len(string.split())
    if video_duration_s and word_count <= _CTA_MAX_WORDS and t_in >= _CTA_LATE_FRACTION * video_duration_s:
        return "cta", 0.5

    return "label", 0.4


def extract_text_layers(normalized_video_path: Path, *, transcript_words: list[dict]) -> list[TextLayer]:
    """Top-level entry point used by trace_builder.py."""
    raise NotImplementedError
