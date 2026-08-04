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
from semantics.providers.base import SemanticProvider
from semantics.schemas import DeepPassPromptInputs, TriagePromptInputs

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
        raise NotImplementedError  # Unit 3.4
