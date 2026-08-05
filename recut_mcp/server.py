"""
L6 - MCP server entry point. See RECUT_SPEC.md sec 9.

Two transports (sec 9.2):
  - stdio, no auth: local mode, default for v1 (see DESIGN_NOTES.md
    "Local-first default")
  - Streamable HTTP, OAuth 2.1: hosted mode, deferred to Phase 4b

Build order (BUILD_ORDER.md Phase 4): stdio first, ship it, THEN build the
HTTP+OAuth transport. Do not build both transports simultaneously - the
tool surface (tools.py) is transport-agnostic by design, so there is no
forced-early-abstraction cost to sequencing it this way.

Uses the official `mcp` PyPI package's high-level MCPServer (Unit 4.6).
NAMING NOTE: this package is named recut_mcp/, not mcp/, specifically so
`import mcp` inside this file (and everywhere else in the project) always
resolves to that real SDK rather than shadowing itself - see
DESIGN_NOTES.md for the collision this was renamed to avoid.
"""

from __future__ import annotations

from mcp.server import MCPServer

from recut_mcp import tools as tools_module
from recut_mcp.resources import PROMPT_NAMES, get_resource, load_prompt

# Every function in tools.py that's part of the actual MCP tool surface -
# wrap_untrusted_text and the private helpers (leading underscore) are
# implementation details, not tools an agent should call directly.
_TOOL_NAMES = [
    "analyze_video",
    "get_job",
    "get_trace",
    "get_template",
    "describe_template",
    "list_slots",
    "register_assets",
    "match_assets",
    "bind",
    "adjust_template",
    "preview",
    "render",
    "get_render",
    "search_library",
]


def _register_tools(server: MCPServer) -> None:
    for tool_name in _TOOL_NAMES:
        fn = getattr(tools_module, tool_name)
        server.add_tool(fn, name=tool_name)


def _register_resources(server: MCPServer) -> None:
    # Three thin wrappers, one per resource type - each just reconstructs
    # the full recut://{type}/{id} URI and delegates to the one, already-
    # tested dispatcher (recut_mcp.resources.get_resource) rather than
    # duplicating its URI-parsing/validation logic here.
    @server.resource("recut://trace/{job_id}")
    def trace_resource(job_id: str) -> bytes:
        return get_resource(f"recut://trace/{job_id}")

    @server.resource("recut://template/{template_id}")
    def template_resource(template_id: str) -> bytes:
        return get_resource(f"recut://template/{template_id}")

    @server.resource("recut://render/{job_id}")
    def render_resource(job_id: str) -> bytes:
        return get_resource(f"recut://render/{job_id}")


def _register_prompts(server: MCPServer) -> None:
    for prompt_name in PROMPT_NAMES:
        prompt_text = load_prompt(prompt_name)

        def _make_prompt_fn(text: str):
            def _prompt_fn() -> str:
                return text

            return _prompt_fn

        server.prompt(name=prompt_name)(_make_prompt_fn(prompt_text))


def build_server() -> MCPServer:
    """Constructs (but does not run) a fully-registered MCPServer - split
    out from run_stdio_server() so a test can build one and inspect its
    registered tools/resources/prompts without actually starting a
    transport loop."""
    server = MCPServer(
        name="recut",
        instructions=(
            "RECUT decomposes a short-form video edit into a machine-readable recipe "
            "(cuts, motion, effects, text, pacing) and re-renders that recipe with "
            "different footage. Use analyze_video to start; see the recreate_this_edit, "
            "explain_this_edit, and find_similar_template prompts for full tool-call flows."
        ),
    )
    _register_tools(server)
    _register_resources(server)
    _register_prompts(server)
    return server


def run_stdio_server() -> None:
    """Registers tools.py's tool surface + resources.py's resources on a
    stdio MCP server. Entry point for local mode."""
    build_server().run(transport="stdio")


def run_http_server(*, host: str, port: int) -> None:
    """Streamable HTTP + OAuth 2.1. Deferred - see module docstring."""
    raise NotImplementedError


if __name__ == "__main__":
    run_stdio_server()
