"""
Primary L2 provider for Phase 3 (see providers/base.py "Interface-now,
implement-later" and DESIGN_NOTES.md). Best fit for the per-shot structured
deep pass on contact sheets (spec sec 4.4).

Before implementing, read the claude-api skill / reference for current
model ids, structured-output patterns, and pricing - do not hand-guess a
model_id string.
"""

from __future__ import annotations

from schemas.models import SemanticShotAnnotation, StyleSummary
from semantics.providers.base import SemanticProvider
from semantics.schemas import DeepPassPromptInputs, TriagePromptInputs


class AnthropicProvider(SemanticProvider):
    model_id = "unset-pin-before-phase-3"

    def triage(self, inputs: TriagePromptInputs) -> StyleSummary:
        raise NotImplementedError

    def deep_pass(self, inputs: DeepPassPromptInputs) -> SemanticShotAnnotation:
        raise NotImplementedError
