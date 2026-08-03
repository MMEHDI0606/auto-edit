"""
Local VLM provider (Qwen-VL / InternVL class) for cost control and for
users unwilling to send third-party video to a hosted API - important for
the local-first deployment posture (see DESIGN_NOTES.md "Local-first
default").

STUB ONLY for the initial scaffold - implement when local-first mode needs
a semantics path that makes no external network call at all. Until then,
local-mode jobs should simply run with the semantics layer disabled
(L1-only trace, no L2 annotations) rather than blocking on this provider.
"""

from __future__ import annotations

from schemas.models import SemanticShotAnnotation, StyleSummary
from semantics.providers.base import SemanticProvider
from semantics.schemas import DeepPassPromptInputs, TriagePromptInputs


class LocalProvider(SemanticProvider):
    model_id = "unset-not-implemented"

    def triage(self, inputs: TriagePromptInputs) -> StyleSummary:
        raise NotImplementedError

    def deep_pass(self, inputs: DeepPassPromptInputs) -> SemanticShotAnnotation:
        raise NotImplementedError
