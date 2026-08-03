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

from pathlib import Path

from schemas.models import TextLayer


def sample_and_ocr(normalized_video_path: Path, *, sample_fps: int) -> list[dict]:
    """Returns raw per-frame OCR boxes: [{t, text, box, conf}, ...]."""
    raise NotImplementedError


def group_into_layers(raw_boxes: list[dict], *, iou_threshold: float = 0.5, string_sim_threshold: float = 0.8) -> list[dict]:
    """Temporal clustering of raw per-frame boxes into candidate layers
    (pre-style-extraction). Kept separate from sample_and_ocr so it can be
    unit tested against synthetic box sequences without running real OCR.
    """
    raise NotImplementedError


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
