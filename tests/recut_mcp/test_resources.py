"""
Unit 4.5 done criteria: get_resource("recut://trace/<job_id>") returns the
full trace bytes for a completed job (the "full trace, but only when
explicitly fetched" path that complements get_trace's summary-only
default). Each prompt file reads as a coherent, correct set of
instructions - verified here by confirming each one actually references
the real tool names its own flow depends on (a human read-through is the
rest of that done criterion, done during authoring).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.store import JobStore, TemplateStore
from recut_mcp.resources import PROMPT_NAMES, get_resource, load_prompt
from schemas.models import AudioRef, Template

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


@pytest.mark.slow
def test_get_resource_trace_returns_full_trace_bytes_for_completed_job(fake_redis_server) -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")
    from recut_mcp.tools import analyze_video

    job_id = analyze_video(str(FIXTURE), depth="fast")["job_id"]

    raw = get_resource(f"recut://trace/{job_id}")
    trace_data = json.loads(raw)
    assert len(trace_data["shots"]) > 0


def test_get_resource_trace_before_done_raises(fake_redis_server) -> None:
    job_id = JobStore().create()
    with pytest.raises(ValueError):
        get_resource(f"recut://trace/{job_id}")


def test_get_resource_template(fake_redis_server) -> None:
    template = Template(source_trace_hash="deadbeef", source_fps=30, slots=[], audio_ref=AudioRef())
    template_id = TemplateStore().create(template)

    raw = get_resource(f"recut://template/{template_id}")
    assert json.loads(raw)["source_trace_hash"] == "deadbeef"


def test_get_resource_render(fake_redis_server, tmp_path) -> None:
    output_path = tmp_path / "out.mp4"
    output_path.write_bytes(b"fake mp4 bytes")

    job_store = JobStore()
    job_id = job_store.create()
    job_store.mark_done(job_id, result_refs={"output_path": str(output_path), "approximations": []})

    assert get_resource(f"recut://render/{job_id}") == b"fake mp4 bytes"


def test_get_resource_rejects_non_recut_scheme() -> None:
    with pytest.raises(ValueError):
        get_resource("https://example.com/trace/123")


def test_get_resource_rejects_malformed_uri() -> None:
    with pytest.raises(ValueError):
        get_resource("recut://trace")  # missing id


def test_get_resource_rejects_unknown_resource_type(fake_redis_server) -> None:
    with pytest.raises(ValueError):
        get_resource("recut://not_a_real_type/some-id")


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_load_prompt_returns_nonempty_text(name: str) -> None:
    text = load_prompt(name)
    assert len(text) > 200  # a real, substantive prompt, not a placeholder


def test_load_prompt_unknown_name_raises() -> None:
    with pytest.raises(ValueError):
        load_prompt("not_a_real_prompt")


def test_recreate_this_edit_references_its_real_tool_sequence() -> None:
    text = load_prompt("recreate_this_edit")
    for tool_name in ["analyze_video", "get_job", "get_template", "register_assets", "match_assets", "bind", "render", "get_render"]:
        assert tool_name in text


def test_explain_this_edit_references_its_real_tool_sequence() -> None:
    text = load_prompt("explain_this_edit")
    for tool_name in ["analyze_video", "get_template", "describe_template", "get_trace"]:
        assert tool_name in text


def test_find_similar_template_references_its_real_tool_sequence() -> None:
    text = load_prompt("find_similar_template")
    for tool_name in ["search_library", "describe_template"]:
        assert tool_name in text
