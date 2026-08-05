"""
L6 - MCP resources: recut://trace/{id}, recut://template/{id},
recut://render/{id} (spec sec 9.3). Resources are how large artifacts
(full traces, rendered video) are addressed without going through a tool
call's return payload - a tool returns a resource URI, the agent fetches
the resource only if/when it actually needs the full content.

Also owns the `recreate_this_edit`, `explain_this_edit`,
`find_similar_template` MCP prompts (spec sec 9.3) - these are prompt
TEMPLATES registered with the server, not Python functions; stored as data
under mcp/prompts/*.md (one file per prompt), not inlined here.
"""

from __future__ import annotations

from pathlib import Path

from api.store import JobStore, TemplateStore

_PROMPTS_DIR = Path(__file__).parent / "prompts"

PROMPT_NAMES = ["recreate_this_edit", "explain_this_edit", "find_similar_template"]


def _get_trace_bytes(job_id: str) -> bytes:
    job = JobStore().get(job_id)
    trace_path = (job.get("result_refs") or {}).get("trace_path")
    if trace_path is None:
        raise ValueError(f"job {job_id!r} has no trace (status={job['status']!r})")
    return Path(trace_path).read_bytes()


def _get_template_bytes(template_id: str) -> bytes:
    return TemplateStore().get(template_id).model_dump_json().encode("utf-8")


def _get_render_bytes(job_id: str) -> bytes:
    job = JobStore().get(job_id)
    output_path = (job.get("result_refs") or {}).get("output_path")
    if output_path is None:
        raise ValueError(f"job {job_id!r} has no rendered output (status={job['status']!r})")
    return Path(output_path).read_bytes()


_DISPATCH = {
    "trace": _get_trace_bytes,
    "template": _get_template_bytes,
    "render": _get_render_bytes,
}


def get_resource(uri: str) -> bytes:
    """Parses recut://{type}/{id} and dispatches to the matching store.
    `type` is one of "trace"/"template"/"render"; `id` is a job_id (for
    trace/render) or template_id (for template)."""
    prefix = "recut://"
    if not uri.startswith(prefix):
        raise ValueError(f"unrecognized resource URI {uri!r} - expected the recut:// scheme")

    parts = uri[len(prefix):].split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"malformed resource URI {uri!r} - expected recut://{{type}}/{{id}}")

    resource_type, resource_id = parts
    handler = _DISPATCH.get(resource_type)
    if handler is None:
        raise ValueError(f"unknown resource type {resource_type!r} in {uri!r}, expected one of {sorted(_DISPATCH)}")

    return handler(resource_id)


def load_prompt(name: str) -> str:
    """Reads one of the authored prompt files (mcp/prompts/{name}.md) -
    used by recut_mcp/server.py (Unit 4.6) to register each as an MCP prompt."""
    if name not in PROMPT_NAMES:
        raise ValueError(f"unknown prompt {name!r}, expected one of {PROMPT_NAMES}")
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
