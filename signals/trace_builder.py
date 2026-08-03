"""
L1 orchestrator - assembles cuts.py + motion.py + text.py + audio.py +
effects.py output into one validated EditTrace (schemas.models.EditTrace).

This is the ONLY function in signals/ that should be called from outside
the package (ingest -> trace_builder -> semantics). Individual extractor
modules are intentionally kept independently unit-testable; this module
owns the ordering constraints between them, specifically:

  1. mask_watermark_regions() must run first and its output frames must be
     what motion.py / text.py operate on (spec sec 8.3).
  2. audio.transcribe() and audio.separate_speech_music() must complete
     before text.classify_role() can be called (role classification needs
     the transcript to distinguish captions from lyrics).
  3. cuts.detect_cuts() must complete before audio.compute_beat_lock()
     (needs cut_times_s).

Failure policy: if any sub-extractor throws, trace_builder does not
silently drop that piece of the trace - it either propagates the error
(preferred, "fail loudly") or, if the extractor supports partial output,
records a confidence-zero placeholder and continues. Decide which per
extractor during Phase 1; do not default to silent partial success.
"""

from __future__ import annotations

from pathlib import Path

from schemas.models import EditTrace


def build_trace(normalized_video_path: Path, wav_path: Path, probe: dict) -> EditTrace:
    """Runs the full L1 pipeline and returns a validated EditTrace.
    Raises pydantic.ValidationError if any sub-extractor produces output
    that doesn't satisfy the schema - this should never happen in
    production and indicates a bug in the extractor, not bad input data.
    """
    raise NotImplementedError
