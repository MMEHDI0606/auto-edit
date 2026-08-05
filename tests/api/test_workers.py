"""
Unit 4.1 done criteria: enqueue an analyze job via a direct Python call,
poll until status=="done", confirm result_refs points at a real trace
file. Both tasks are called directly as plain functions here (not via
.delay()) - Celery-decorated functions remain directly callable, and per
Unit 4.1's own done criteria this is exactly the acceptable "direct Python
call" path, no broker/worker process needed.

Marked slow: analyze_video_task runs the REAL ingest/normalize/probe/
build_trace pipeline against the existing synthetic_clip.mp4 fixture (see
tests/signals/test_trace_builder.py for the same real-pipeline pattern);
render_task runs the real ffmpeg engine.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from api.store import JobStore, TemplateStore
from api.workers import analyze_video_task, render_task
from schemas.models import (
    AssetBinding,
    BindingSet,
    DurationFlex,
    MotionCurve,
    MotionPrimitive,
    Slot,
    SlotApplied,
    SlotRequirements,
    Template,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


@pytest.mark.slow
def test_analyze_video_task_fast_depth_produces_a_real_trace_file(fake_redis_server) -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    job_store = JobStore()
    job_id = job_store.create()

    analyze_video_task(job_id, str(FIXTURE), "fast")

    job = job_store.get(job_id)
    assert job["status"] == "done"
    assert job["progress"] == 1.0
    trace_path = Path(job["result_refs"]["trace_path"])
    assert trace_path.exists()
    trace_data = json.loads(trace_path.read_text())
    assert len(trace_data["shots"]) > 0
    assert "template_id" not in job["result_refs"]  # depth="fast" - no L3 compile


@pytest.mark.slow
def test_analyze_video_task_full_depth_also_persists_a_template(fake_redis_server) -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    job_store = JobStore()
    job_id = job_store.create()

    analyze_video_task(job_id, str(FIXTURE), "full")

    job = job_store.get(job_id)
    assert job["status"] == "done"
    template_id = job["result_refs"]["template_id"]
    template = TemplateStore().get(template_id)
    assert len(template.slots) > 0


@pytest.mark.slow
def test_analyze_video_task_on_missing_file_marks_job_as_error(fake_redis_server) -> None:
    job_store = JobStore()
    job_id = job_store.create()

    with pytest.raises(FileNotFoundError):
        analyze_video_task(job_id, "/no/such/file.mp4", "fast")

    job = job_store.get(job_id)
    assert job["status"] == "error"
    assert job["error"]


def _make_asset_clip(path: Path, color: str, duration_s: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x568:d={duration_s}:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True, text=True,
    )


@pytest.mark.slow
def test_render_task_produces_a_real_output_file(fake_redis_server, tmp_path) -> None:
    clip = tmp_path / "clip.mp4"
    _make_asset_clip(clip, "red", 1.0)

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
                human_instruction="test",
            )
        ],
        audio_ref={"beat_grid_s": []},
    )
    bindings = BindingSet(
        binding_id="b1",
        bindings=[
            AssetBinding(
                slot_id="slot_01", asset_id=str(clip), in_point_s=0.0, duration_s=1.0, confidence=0.9, rationale="test"
            )
        ],
        unresolved_slots=[],
    )

    job_store = JobStore()
    job_id = job_store.create()
    out_path = tmp_path / "out.mp4"

    render_task(
        job_id,
        template.model_dump_json(),
        bindings.model_dump_json(),
        {"resolution": [320, 568], "output_path": str(out_path)},
    )

    job = job_store.get(job_id)
    assert job["status"] == "done"
    assert Path(job["result_refs"]["output_path"]).exists()
