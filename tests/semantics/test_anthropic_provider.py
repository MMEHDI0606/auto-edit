"""
Unit 3.3 - AnthropicProvider.triage(). The unit's actual done criterion
("running triage() against 3-5 real videos produces a plausible
StyleSummary") needs a real ANTHROPIC_API_KEY and real short-form video
content - blocked the same way the Phase 1/2 gates are (see
eval/golden/NEEDS_INPUT.md), not something to fabricate here.

What CAN be verified without real credentials/video: the request is built
correctly (structured-output schema, image block, prompt content) and the
response is parsed correctly into a StyleSummary - by injecting a fake
Anthropic client instead of hitting the real API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image

from schemas.models import SemanticShotAnnotation, StyleSummary
from semantics.providers.anthropic_provider import _DEEP_PASS_JSON_SCHEMA, _TRIAGE_JSON_SCHEMA, AnthropicProvider
from semantics.schemas import DeepPassPromptInputs, TriagePromptInputs


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text=text)]


class _FakeMessages:
    """Fake `client.messages`. `responses` may be a single dict (returned
    every call, JSON-encoded) or a list of dict/raw-str items consumed in
    call order (last item repeats once exhausted) - the list form is what
    the repair-retry tests need: a malformed raw string on the first call,
    valid JSON on the second."""

    def __init__(self, responses) -> None:
        self._responses = responses if isinstance(responses, list) else [responses]
        self._call_index = 0
        self.call_history: list[dict] = []

    @property
    def last_call_kwargs(self) -> dict | None:
        return self.call_history[-1] if self.call_history else None

    def create(self, **kwargs):
        self.call_history.append(kwargs)
        item = self._responses[min(self._call_index, len(self._responses) - 1)]
        self._call_index += 1
        text = item if isinstance(item, str) else json.dumps(item)
        return _FakeResponse(text)


class _FakeAnthropicClient:
    def __init__(self, responses) -> None:
        self.messages = _FakeMessages(responses)


@pytest.fixture()
def whole_video_sheet_path(tmp_path) -> Path:
    path = tmp_path / "whole_video_sheet.png"
    Image.new("RGB", (16, 16), color="blue").save(path)
    return path


def test_triage_sends_correct_structured_output_request(whole_video_sheet_path) -> None:
    fake_client = _FakeAnthropicClient(
        {"genre": "comedy skit", "hook_type": "in-media-res action", "pacing_description": "fast, sub-second cuts"}
    )
    provider = AnthropicProvider(client=fake_client)

    provider.triage(
        TriagePromptInputs(whole_video_low_res_sheet_path=str(whole_video_sheet_path), duration_s=12.5, tempo_bpm=128.0)
    )

    kwargs = fake_client.messages.last_call_kwargs
    assert kwargs["model"] == AnthropicProvider.model_id == "claude-sonnet-5"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["output_config"]["format"]["schema"] == _TRIAGE_JSON_SCHEMA

    content = kwargs["messages"][0]["content"]
    image_block = next(block for block in content if block["type"] == "image")
    assert image_block["source"]["media_type"] == "image/png"
    import base64

    assert image_block["source"]["data"] == base64.standard_b64encode(whole_video_sheet_path.read_bytes()).decode("utf-8")

    text_block = next(block for block in content if block["type"] == "text")
    assert "12.5" in text_block["text"]
    assert "128.0 BPM" in text_block["text"]


def test_triage_handles_missing_tempo_bpm(whole_video_sheet_path) -> None:
    fake_client = _FakeAnthropicClient({"genre": "g", "hook_type": "h", "pacing_description": "p"})
    provider = AnthropicProvider(client=fake_client)

    provider.triage(
        TriagePromptInputs(whole_video_low_res_sheet_path=str(whole_video_sheet_path), duration_s=5.0, tempo_bpm=None)
    )

    text_block = next(
        block for block in fake_client.messages.last_call_kwargs["messages"][0]["content"] if block["type"] == "text"
    )
    assert "unknown" in text_block["text"]


def test_triage_parses_response_into_style_summary(whole_video_sheet_path) -> None:
    fake_client = _FakeAnthropicClient(
        {"genre": "product review", "hook_type": "direct address question", "pacing_description": "slow build"}
    )
    provider = AnthropicProvider(client=fake_client)

    result = provider.triage(
        TriagePromptInputs(whole_video_low_res_sheet_path=str(whole_video_sheet_path), duration_s=20.0, tempo_bpm=90.0)
    )

    assert result == StyleSummary(
        genre="product review",
        hook_type="direct address question",
        pacing_description="slow build",
        model_id="claude-sonnet-5",
    )


@pytest.fixture()
def contact_sheet_path(tmp_path) -> Path:
    path = tmp_path / "shot1_contact_sheet.png"
    Image.new("RGB", (48, 16), color="red").save(path)
    return path


def _deep_pass_inputs(contact_sheet_path: Path, **overrides) -> DeepPassPromptInputs:
    defaults = dict(
        shot_id="shot1",
        contact_sheet_path=str(contact_sheet_path),
        allowed_effect_labels=["freeze", "cut", "static"],
        ocr_strings=["HOOK TEXT"],
        transcript_snippet="hey guys watch this",
    )
    defaults.update(overrides)
    return DeepPassPromptInputs(**defaults)


def test_deep_pass_sends_allowed_labels_ocr_and_transcript_in_prompt(contact_sheet_path) -> None:
    fake_client = _FakeAnthropicClient({"role": "hook", "role_confidence": 0.9})
    provider = AnthropicProvider(client=fake_client)

    provider.deep_pass(_deep_pass_inputs(contact_sheet_path))

    kwargs = fake_client.messages.last_call_kwargs
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["output_config"]["format"]["schema"] == _DEEP_PASS_JSON_SCHEMA
    text_block = next(b for b in kwargs["messages"][0]["content"] if b["type"] == "text")
    assert "freeze, cut, static" in text_block["text"]
    assert "HOOK TEXT" in text_block["text"]
    assert "hey guys watch this" in text_block["text"]


def test_deep_pass_parses_response_into_semantic_shot_annotation(contact_sheet_path) -> None:
    fake_client = _FakeAnthropicClient({"role": "hook", "role_confidence": 0.9})
    provider = AnthropicProvider(client=fake_client)

    result = provider.deep_pass(_deep_pass_inputs(contact_sheet_path))

    assert result == SemanticShotAnnotation(shot_id="shot1", role="hook", role_confidence=0.9, model_id="claude-sonnet-5")


def test_deep_pass_repairs_once_on_malformed_json_then_succeeds(contact_sheet_path) -> None:
    fake_client = _FakeAnthropicClient(["not valid json at all", {"role": "reaction", "role_confidence": 0.7}])
    provider = AnthropicProvider(client=fake_client)

    result = provider.deep_pass(_deep_pass_inputs(contact_sheet_path))

    assert result.role == "reaction"
    assert len(fake_client.messages.call_history) == 2
    repair_prompt = next(
        b["text"] for b in fake_client.messages.call_history[1]["messages"][0]["content"] if b["type"] == "text"
    )
    assert "failed validation" in repair_prompt


def test_deep_pass_raises_after_second_malformed_response(contact_sheet_path) -> None:
    from pydantic import ValidationError

    fake_client = _FakeAnthropicClient(["still not json", "still not json either"])
    provider = AnthropicProvider(client=fake_client)

    with pytest.raises(ValidationError):
        provider.deep_pass(_deep_pass_inputs(contact_sheet_path))

    assert len(fake_client.messages.call_history) == 2

