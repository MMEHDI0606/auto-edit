"""
Celery/RQ + Redis task definitions: analyze_video_task, render_task, etc.
Each task wraps one pipeline stage (ingest -> signal -> semantics ->
compiler, or matcher -> render) and writes progress into the job store so
mcp.tools.get_job / get_render can poll it (spec sec 9.4: everything
long-running is async, MCP clients time out otherwise).
"""

from __future__ import annotations

from pathlib import Path

from api.celery_app import celery_app
from api.pipeline import run_analysis, run_render
from api.store import JobStore, TemplateStore
from render.interface import RenderOptions
from schemas.models import BindingSet, Template


@celery_app.task(name="recut.analyze_video")
def analyze_video_task(job_id: str, source: str, depth: str) -> None:
    job_store = JobStore()
    try:
        def on_progress(stage: str, progress: float) -> None:
            job_store.mark_running(job_id, stage=stage, progress=progress)

        result = run_analysis(source, depth=depth, on_progress=on_progress)

        result_refs: dict = {"trace_path": result["trace_path"], "content_hash": result["content_hash"]}
        if result["template"] is not None:
            template_id = TemplateStore().create(result["template"])
            result_refs["template_id"] = template_id

        job_store.mark_done(job_id, result_refs=result_refs)
    except Exception as exc:
        job_store.mark_error(job_id, error=str(exc))
        raise


@celery_app.task(name="recut.render")
def render_task(job_id: str, template_json: str, bindings_json: str, opts: dict) -> None:
    """`template`/`bindings` are passed pre-serialized (Celery tasks must
    only receive JSON-safe arguments, not live Pydantic objects) - the
    caller (mcp.tools.render(), Unit 4.4) is responsible for the
    template_id/binding_id -> object lookup before enqueueing."""
    job_store = JobStore()
    try:
        def on_progress(stage: str, progress: float) -> None:
            job_store.mark_running(job_id, stage=stage, progress=progress)

        template = Template.model_validate_json(template_json)
        bindings = BindingSet.model_validate_json(bindings_json)
        output_path = opts.get("output_path")
        render_opts = RenderOptions(
            include_audio=opts.get("include_audio", False),
            resolution=tuple(opts.get("resolution", (1080, 1920))),
            output_path=Path(output_path) if output_path else None,
        )

        report = run_render(template, bindings, render_opts, on_progress=on_progress)

        job_store.mark_done(
            job_id,
            result_refs={
                "output_path": str(report.output_path),
                "approximations": report.approximations,
            },
        )
    except Exception as exc:
        job_store.mark_error(job_id, error=str(exc))
        raise
