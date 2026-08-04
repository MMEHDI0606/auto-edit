"""
L2-specific request/response shapes for provider calls (prompts, raw model
JSON before validation). These are NOT the persisted contract - the
persisted/versioned semantic output is SemanticAnnotations in
schemas/models.py. Keep that separation: this file can change per-provider
without touching the versioned schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, confloat


@dataclass
class TriagePromptInputs:
    whole_video_low_res_sheet_path: str
    duration_s: float
    tempo_bpm: float | None


@dataclass
class DeepPassPromptInputs:
    shot_id: str
    contact_sheet_path: str
    allowed_effect_labels: list[str]  # THE evidence gate input, see gating.py
    ocr_strings: list[str]
    transcript_snippet: str | None


class DeepPassModelOutput(BaseModel):
    """The raw shape a deep-pass model call actually produces - just the
    fields the model itself asserts. `shot_id`/`model_id` on the persisted
    SemanticShotAnnotation are filled in by the caller, not requested from
    the model (same pattern as StyleSummary.model_id in the triage pass).
    This is also the schema `gating.repair_or_fail()` validates against."""

    role: Optional[str] = None
    role_confidence: confloat(ge=0, le=1) = 0.0
