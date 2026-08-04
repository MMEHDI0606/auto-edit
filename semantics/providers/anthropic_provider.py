"""
Primary L2 provider for Phase 3 (see providers/base.py "Interface-now,
implement-later" and DESIGN_NOTES.md). Best fit for the per-shot structured
deep pass on contact sheets (spec sec 4.4).

Before implementing, read the claude-api skill / reference for current
model ids, structured-output patterns, and pricing - do not hand-guess a
model_id string.

MODEL ID PIN (Unit 3.3): verified live via WebFetch against
https://platform.claude.com/docs/en/about-claude/models/overview.md rather
than trusting the repo-cloned skills/ai-agent-foundation-template snapshot
(dated - it still lists Sonnet 4.6 as "current"). Confirmed there: Claude
Sonnet 5's Claude API ID AND alias are both the dateless string
"claude-sonnet-5" - per that page's own note, dateless IDs (introduced with
the 4.6 generation) are pinned snapshots, not evergreen pointers, so this
is a real pin, not a floating alias. Chosen over Opus 5 (higher cost, not
needed for per-shot/whole-video contact-sheet labeling) and Haiku 4.5 (spec
sec 4.4 wants "the best combination of speed and intelligence" for this
per-video/per-shot volume, not the cheapest-possible tier).

Structured output mechanism confirmed live via WebFetch against
https://platform.claude.com/docs/en/build-with-claude/structured-outputs.md:
Claude API structured outputs (`output_config.format`, `type: json_schema`)
is GA for "Claude 4.5 and later", which covers Sonnet 5 - this is used
instead of free-text parsing, per Unit 3.3's own instruction.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import anthropic

from schemas.models import SemanticShotAnnotation, StyleSummary
from semantics.gating import repair_or_fail
from semantics.providers.base import SemanticProvider
from semantics.schemas import DeepPassModelOutput, DeepPassPromptInputs, TriagePromptInputs

_TRIAGE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "genre": {"type": "string", "description": "Overall content genre, e.g. 'comedy skit', 'product review'"},
        "hook_type": {
            "type": "string",
            "description": "How the opening seconds grab attention, e.g. 'in-media-res action', 'direct address question'",
        },
        "pacing_description": {
            "type": "string",
            "description": "Overall cutting rhythm/pacing in plain language, e.g. 'fast, sub-second cuts throughout'",
        },
    },
    "required": ["genre", "hook_type", "pacing_description"],
    "additionalProperties": False,
}

_TRIAGE_MAX_TOKENS = 1024

_DEEP_PASS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "role": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": (
                "This shot's narrative role, e.g. 'hook', 'before_state', 'reveal', 'reaction', or null if "
                "none applies. If describing any effect/transition/camera-motion quality, ONLY use a label "
                "from the allowed_effect_labels list given in the prompt - never one absent from it."
            ),
        },
        "role_confidence": {"type": "number", "description": "0..1 confidence in the role label"},
    },
    "required": ["role", "role_confidence"],
    "additionalProperties": False,
}

_DEEP_PASS_MAX_TOKENS = 1024


class AnthropicProvider(SemanticProvider):
    model_id = "claude-sonnet-5"

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        # Accepts an injected client so tests can pass a fake/mock without
        # touching real credentials or the network (this provider itself
        # never mocks output - it's the caller's choice in a test).
        self._client = client or anthropic.Anthropic()

    def triage(self, inputs: TriagePromptInputs) -> StyleSummary:
        image_bytes = Path(inputs.whole_video_low_res_sheet_path).read_bytes()
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        tempo_text = f"{inputs.tempo_bpm:.1f} BPM" if inputs.tempo_bpm is not None else "unknown"

        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=_TRIAGE_MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                        },
                        {
                            "type": "text",
                            "text": (
                                "This is a tiled contact sheet sampling roughly one frame per second "
                                f"across an entire short-form video edit. Duration: {inputs.duration_s:.1f}s. "
                                f"Tempo: {tempo_text}. Describe the overall genre, the type of opening hook "
                                "used, and the pacing style. Base every claim only on what is visible in the "
                                "tiles or the stated duration/tempo - do not invent details you cannot see."
                            ),
                        },
                    ],
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": _TRIAGE_JSON_SCHEMA}},
        )

        raw_text = next(block.text for block in response.content if block.type == "text")
        parsed = json.loads(raw_text)
        return StyleSummary(**parsed, model_id=self.model_id)

    def deep_pass(self, inputs: DeepPassPromptInputs) -> SemanticShotAnnotation:
        image_bytes = Path(inputs.contact_sheet_path).read_bytes()
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        def build_prompt_text(repair_note: str | None) -> str:
            ocr_text = "; ".join(inputs.ocr_strings) if inputs.ocr_strings else "(none detected)"
            transcript_text = inputs.transcript_snippet or "(none)"
            allowed_text = ", ".join(inputs.allowed_effect_labels) if inputs.allowed_effect_labels else "(none)"
            text = (
                "This is a contact sheet of one shot's first/middle/last frame, timestamps burned in. "
                f"On-screen text (OCR, may contain errors): {ocr_text}. "
                f"Speech transcript snippet: {transcript_text}. "
                "Describe this shot's narrative role (e.g. 'hook', 'before_state', 'reveal', 'reaction') if "
                "one clearly applies, or null if none does. If your description references any effect, "
                "transition, or camera-motion quality, you may ONLY use one of these evidence-backed labels: "
                f"{allowed_text}. Never claim an effect/transition/motion label not in that list - it was not "
                "detected on this shot."
            )
            if repair_note:
                text += (
                    f"\n\nYour previous response failed validation: {repair_note}\n"
                    "Return corrected JSON matching the schema."
                )
            return text

        def call(repair_note: str | None = None) -> str:
            response = self._client.messages.create(
                model=self.model_id,
                max_tokens=_DEEP_PASS_MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                            },
                            {"type": "text", "text": build_prompt_text(repair_note)},
                        ],
                    }
                ],
                output_config={"format": {"type": "json_schema", "schema": _DEEP_PASS_JSON_SCHEMA}},
            )
            return next(block.text for block in response.content if block.type == "text")

        raw = call()
        validated = repair_or_fail(raw, DeepPassModelOutput, retry_fn=call)
        return SemanticShotAnnotation(shot_id=inputs.shot_id, model_id=self.model_id, **validated)
