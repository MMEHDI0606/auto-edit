"""
Unit 4.4 done criteria: full end-to-end MCP-tool-level flow - analyze ->
template -> register assets -> match -> bind -> render (with a retried
duplicate call using the same idempotency_key confirmed to NOT create a
second render job) -> get_render returns a playable URL + report.

Uses the ffmpeg render engine (not the default "remotion") - overridden
via RECUT_PRIMARY_RENDER_ENGINE so this test doesn't need a Node/npx
toolchain, matching how tests/render/test_ffmpeg_engine.py already
exercises the same engine directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.store import BindingStore, TemplateStore
from common.config import load_settings
from recut_mcp.tools import (
    analyze_video,
    bind,
    get_job,
    get_render,
    get_template,
    match_assets,
    preview,
    register_assets,
    render,
    search_library,
)

NO_FACE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


@pytest.fixture()
def ffmpeg_render_engine(monkeypatch):
    monkeypatch.setenv("RECUT_PRIMARY_RENDER_ENGINE", "ffmpeg")
    load_settings.cache_clear()
    yield
    load_settings.cache_clear()


@pytest.mark.slow
def test_full_flow_analyze_to_get_render(fake_redis_server, ffmpeg_render_engine) -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    analyze_result = analyze_video(str(NO_FACE_FIXTURE), depth="full")
    job_id = analyze_result["job_id"]
    assert get_job(job_id)["status"] == "done"

    template_result = get_template(job_id)
    template_id = template_result["template_id"]
    assert len(template_result["template"]["slots"]) > 0

    asset_ids = register_assets([str(NO_FACE_FIXTURE), str(NO_FACE_FIXTURE)])

    proposal = match_assets(template_id, asset_ids)
    slot_to_asset = {b["slot_id"]: b["asset_id"] for b in proposal["proposed_bindings"]}
    assert slot_to_asset  # at least one slot should resolve against 2 identical assets

    binding_id = bind(template_id, slot_to_asset)
    persisted_binding = BindingStore().get(binding_id)
    assert persisted_binding.template_id == template_id

    storyboard_uri = preview(binding_id)
    assert Path(storyboard_uri).exists()

    render_result_1 = render(binding_id, resolution=(320, 568), idempotency_key="test-key-1")
    render_job_id = render_result_1["job_id"]

    # Retried call, same idempotency_key - must NOT create a second render job.
    render_result_2 = render(binding_id, resolution=(320, 568), idempotency_key="test-key-1")
    assert render_result_2["job_id"] == render_job_id

    render_job = get_job(render_job_id)
    assert render_job["status"] == "done"

    result = get_render(render_job_id)
    assert Path(result["url"]).exists()
    assert "approximations" in result["render_report"]


def test_render_before_binding_exists_raises(fake_redis_server, ffmpeg_render_engine) -> None:
    with pytest.raises(KeyError):
        render("nonexistent-binding", idempotency_key="k1")


def test_get_render_before_done_raises(fake_redis_server) -> None:
    from api.store import JobStore

    job_id = JobStore().create()
    with pytest.raises(ValueError):
        get_render(job_id)


def test_search_library_empty_when_no_templates_persisted(fake_redis_server) -> None:
    assert search_library("anything") == []


def test_search_library_finds_persisted_templates_by_instruction_text(fake_redis_server) -> None:
    from schemas.models import (
        AudioRef,
        DurationFlex,
        MotionCurve,
        MotionPrimitive,
        Slot,
        SlotApplied,
        SlotRequirements,
        Template,
    )

    template = Template(
        source_trace_hash="deadbeef",
        source_fps=30,
        slots=[
            Slot(
                slot_id="slot_01",
                order=1,
                duration_s=1.0,
                duration_flex=DurationFlex(min_s=0.75, max_s=1.25, snap="none"),
                requirements=SlotRequirements(),
                applied=SlotApplied(motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01)),
                human_instruction="This is your hook shot (~1.0s).",
            )
        ],
        audio_ref=AudioRef(),
    )
    template_id = TemplateStore().create(template)

    assert search_library("hook") == [{"template_id": template_id, "slot_count": 1}]
    assert search_library("nonexistent phrase") == []
    assert search_library("") == [{"template_id": template_id, "slot_count": 1}]
