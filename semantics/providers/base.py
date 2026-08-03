"""
L2 provider interface. See RECUT_SPEC.md sec 4.4: "Make the model layer an
interface with 3 implementations. Do not hard-couple to one vendor - this
is your most volatile dependency."

SCOPE NOTE (see DESIGN_NOTES.md "Interface-now, implement-later"): define
this interface fully now, but in Phase 3 implement ONLY ONE concrete
provider fully (recommend Anthropic, since contact-sheet + structured JSON
output is exactly Claude's strength and it keeps the eval loop
single-vendor while it's being built). Stub gemini_provider.py and
local_provider.py as interface-conformant placeholders that raise
NotImplementedError, and only fill them in when a second provider is
actually needed (cost comparison, or a local-only privacy requirement).
Building all three fully before Phase 3 ships anything is exactly the kind
of premature abstraction spend this project can't afford yet.

Every implementation MUST:
  - accept and return only the dataclasses in semantics/schemas.py (never
    leak a provider SDK type across this boundary)
  - record `model_id` (exact pinned version string) in every response
  - raise on malformed JSON rather than best-effort parsing (gating.py
    owns the repair-retry policy, not this layer)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from schemas.models import SemanticShotAnnotation, StyleSummary
from semantics.schemas import DeepPassPromptInputs, TriagePromptInputs


class SemanticProvider(ABC):
    model_id: str  # pinned, e.g. "claude-sonnet-5-20260201" - never a floating alias

    @abstractmethod
    def triage(self, inputs: TriagePromptInputs) -> StyleSummary:
        """Cheap, whole-video-contact-sheet pass: genre, hook type, pacing."""

    @abstractmethod
    def deep_pass(self, inputs: DeepPassPromptInputs) -> SemanticShotAnnotation:
        """Per-shot structured pass, called only where L1 confidence is low
        or content labelling is needed (spec sec 4.2) - trigger policy lives
        in the caller (semantics package top-level), not in the provider."""
