"""
Celery/RQ + Redis task definitions: analyze_video_task, render_task, etc.
Each task wraps one pipeline stage (ingest -> signal -> semantics ->
compiler, or matcher -> render) and writes progress into the job store so
mcp.tools.get_job / get_render can poll it (spec sec 9.4: everything
long-running is async, MCP clients time out otherwise).
"""

from __future__ import annotations


def analyze_video_task(job_id: str, source: str, depth: str) -> None:
    raise NotImplementedError


def render_task(job_id: str, binding_id: str, opts: dict) -> None:
    raise NotImplementedError
