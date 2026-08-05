"""
Unit 4.2 done criteria: from a test client (not yet a real MCP client),
call analyze_video -> poll get_job to completion -> call get_trace with no
sections arg (confirm it's small/summary-shaped) and with
sections=["shots"] (confirm only shots come back, and any text strings
within are wrapped).

Marked slow where it runs the real analyze pipeline against the existing
synthetic_clip.mp4 fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from recut_mcp.tools import analyze_video, get_job, get_trace, wrap_untrusted_text

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


def test_analyze_video_returns_job_id_immediately(fake_redis_server) -> None:
    result = analyze_video(str(FIXTURE), depth="fast")
    assert "job_id" in result


def test_get_job_for_unknown_job_raises(fake_redis_server) -> None:
    with pytest.raises(KeyError):
        get_job("nonexistent")


def test_get_trace_before_job_done_raises(fake_redis_server) -> None:
    from api.store import JobStore

    job_id = JobStore().create()  # still "pending" - never ran the task
    with pytest.raises(ValueError):
        get_trace(job_id)


@pytest.mark.slow
def test_analyze_then_get_trace_summary_and_sections(fake_redis_server) -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    result = analyze_video(str(FIXTURE), depth="fast")
    job_id = result["job_id"]

    job = get_job(job_id)
    assert job["status"] == "done"  # task_always_eager - already ran synchronously

    summary = get_trace(job_id)
    assert set(summary.keys()) == {"shot_count", "duration_s", "evidence", "resource_uri"}
    assert summary["shot_count"] > 0
    assert summary["resource_uri"] == f"recut://trace/{job_id}"

    sectioned = get_trace(job_id, sections=["shots"])
    assert set(sectioned.keys()) == {"shots"}
    assert len(sectioned["shots"]) == summary["shot_count"]


@pytest.mark.slow
def test_get_trace_text_layers_section_wraps_ocr_strings(fake_redis_server) -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    result = analyze_video(str(FIXTURE), depth="fast")
    job_id = result["job_id"]

    sectioned = get_trace(job_id, sections=["text_layers"])
    assert set(sectioned.keys()) == {"text_layers"}
    assert len(sectioned["text_layers"]) > 0  # synthetic_clip.mp4 has "HOOK TEXT" burned in

    for layer in sectioned["text_layers"]:
        assert layer["string"] == wrap_untrusted_text(layer["string"]["untrusted_source_text"])


def test_get_trace_rejects_unknown_section(fake_redis_server) -> None:
    from api.store import JobStore

    job_store = JobStore()
    job_id = job_store.create()
    job_store.mark_done(job_id, result_refs={"trace_path": "/does/not/matter"})

    with pytest.raises(ValueError):
        get_trace(job_id, sections=["not_a_real_section"])
