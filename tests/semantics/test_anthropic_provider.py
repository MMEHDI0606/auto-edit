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

from schemas.models import StyleSummary
from semantics.providers.anthropic_provider import _TRIAGE_JSON_SCHEMA, AnthropicProvider
from semantics.schemas import TriagePromptInputs


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.content = [_FakeTextBlock(text=json.dumps(payload))]


class _FakeMessages:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_call_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return _FakeResponse(self._payload)


class _FakeAnthropicClient:
    def __init__(self, payload: dict) -> None:
        self.messages = _FakeMessages(payload)


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


def test_deep_pass_still_not_implemented_until_unit_3_4(whole_video_sheet_path) -> None:
    provider = AnthropicProvider(client=_FakeAnthropicClient({}))
    with pytest.raises(NotImplementedError):
        provider.deep_pass(None)  # type: ignore[arg-type]
