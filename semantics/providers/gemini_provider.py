"""
Secondary L2 provider - native video input, configurable FPS/clipping,
large context; best fit for the triage pass on raw video (spec sec 4.4).

STUB ONLY for the initial scaffold - see providers/base.py
"Interface-now, implement-later". Do not implement until Phase 3 actually
needs a second provider (cost/quality comparison against the Anthropic
provider, or a triage-on-raw-video path that skips contact-sheet building).
"""

from __future__ import annotations

from schemas.models import SemanticShotAnnotation, StyleSummary
from semantics.providers.base import SemanticProvider
from semantics.schemas import DeepPassPromptInputs, TriagePromptInputs


class GeminiProvider(SemanticProvider):
    model_id = "unset-not-implemented"

    def triage(self, inputs: TriagePromptInputs) -> StyleSummary:
        raise NotImplementedError

    def deep_pass(self, inputs: DeepPassPromptInputs) -> SemanticShotAnnotation:
        raise NotImplementedError
