"""
Shared business logic behind api/workers.py's Celery tasks (and, later,
any other caller that needs the same pipeline outside a request/response
cycle). Calls Phase 1-3's real functions directly - the same primitives
cli/analyze.py wires up for the CLI entry point (ingest.downloader.fetch,
ingest.normalize.normalize/probe, signals.trace_builder.build_trace,
compiler.template.compile_template) - just callable from a progress-
reporting, job-store-aware caller instead of argparse/sys.exit.

Semantics (Phase 3, Units 3.2-3.4) are NOT wired into depth="full" here:
they need a real ANTHROPIC_API_KEY, which is not present in this
environment (see eval/golden/NEEDS_INPUT.md's Unit 3.3 entry) - depth="full"
means "also compile a Template from the L1 trace alone" (compile_template
already runs standalone with semantics=None), not "also run the VLM." Wire
semantics in here once a real key exists; the call site is a single
optional step, not a redesign.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Literal, TypedDict

from common.config import load_settings
from compiler.template import compile_template
from ingest import cache as cache_mod
from ingest.downloader import fetch
from ingest.normalize import normalize, probe
from render.interface import RenderOptions, RenderReport, get_engine
from schemas.models import BindingSet, EditTrace, Template
from signals.trace_builder import build_trace

ProgressFn = Callable[[str, float], None]


class AnalysisResult(TypedDict):
    trace_path: str
    content_hash: str
    template: Template | None


def _noop_progress(stage: str, progress: float) -> None:
    return None


def _resolve_source(source: str, download_dir: Path) -> Path:
    if source.startswith("http://") or source.startswith("https://"):
        return fetch(source, download_dir).local_path
    local_path = Path(source)
    if not local_path.exists():
        raise FileNotFoundError(f"file not found: {local_path}")
    return local_path


def run_analysis(
    source: str, *, depth: Literal["fast", "full"] = "full", on_progress: ProgressFn | None = None
) -> AnalysisResult:
    """Ingest -> normalize -> probe -> L1 trace, then (depth="full" only)
    L3 template compilation. Returns the trace's on-disk path (already
    cache-persisted by ingest.cache), its content hash, and the compiled
    Template object itself (None for depth="fast") - the caller decides
    how/whether to persist the Template (e.g. into api.store.TemplateStore)."""
    progress = on_progress or _noop_progress
    settings = load_settings()

    with tempfile.TemporaryDirectory(prefix="recut_job_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        progress("ingest", 0.0)
        local_path = _resolve_source(source, tmp_path)

        source_hash = cache_mod.hash_file(local_path)
        cached = cache_mod.get(source_hash)
        if cached is not None and cached.trace_path is not None:
            trace = EditTrace.model_validate_json(cached.trace_path.read_text())
            template = compile_template(trace) if depth == "full" else None
            progress("done", 1.0)
            return {"trace_path": str(cached.trace_path), "content_hash": str(source_hash), "template": template}

        progress("normalize", 0.2)
        norm_result = normalize(
            local_path,
            tmp_path / "normalized",
            fps=settings.normalize_fps,
            width=settings.normalize_width,
            height=settings.normalize_height,
            crf=settings.normalize_crf,
        )

        progress("probe", 0.4)
        probe_dict = probe(norm_result.normalized_path)

        progress("trace", 0.6)
        trace = build_trace(norm_result.normalized_path, norm_result.wav_path, probe_dict)

        cache_dir = Path(settings.cache_root) / source_hash
        cache_dir.mkdir(parents=True, exist_ok=True)
        trace_path = cache_dir / "trace.json"
        trace_path.write_text(trace.model_dump_json(indent=2))
        cache_mod.put(
            source_hash,
            cache_mod.CacheEntry(
                content_hash=source_hash,
                normalized_video_path=norm_result.normalized_path,
                wav_path=norm_result.wav_path,
                probe_json_path=cache_mod.write_probe_json(source_hash, probe_dict),
                trace_path=trace_path,
            ),
        )

        template: Template | None = None
        if depth == "full":
            progress("compile", 0.8)
            template = compile_template(trace)

        progress("done", 1.0)
        return {"trace_path": str(trace_path), "content_hash": str(source_hash), "template": template}


def run_render(
    template: Template, bindings: BindingSet, opts: RenderOptions, *, on_progress: ProgressFn | None = None
) -> RenderReport:
    """Thin wrapper over render.interface.get_engine(...).render() - exists
    so api/workers.py's render_task has the same "call the shared pipeline
    function" shape as run_analysis(), rather than reaching into render/
    directly."""
    progress = on_progress or _noop_progress
    progress("render", 0.0)
    engine = get_engine(load_settings().primary_render_engine)
    report = engine.render(template, bindings, opts)
    progress("done", 1.0)
    return report
