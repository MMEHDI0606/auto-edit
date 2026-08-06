"""
L6 - MCP server entry point. See RECUT_SPEC.md sec 9.

Two transports (sec 9.2):
  - stdio, no auth: local mode, default for v1 (see DESIGN_NOTES.md
    "Local-first default")
  - Streamable HTTP, OAuth 2.1: hosted mode (Unit 4.7, Phase 4b) - gated
    behind an explicit decision to actually pursue hosted mode, per that
    unit's own instruction; built once that decision was made.

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
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from common.config import load_settings
from recut_mcp import tools as tools_module
from recut_mcp.auth import MissingAuthCredentialsError, RecutOAuthProvider, _set_active_provider
from recut_mcp.resources import PROMPT_NAMES, get_resource, load_prompt

_INSTRUCTIONS = (
    "RECUT decomposes a short-form video edit into a machine-readable recipe "
    "(cuts, motion, effects, text, pacing) and re-renders that recipe with "
    "different footage. Use analyze_video to start; see the recreate_this_edit, "
    "explain_this_edit, and find_similar_template prompts for full tool-call flows."
)

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
    """Constructs (but does not run) a fully-registered, no-auth MCPServer
    for the stdio transport - split out from run_stdio_server() so a test
    can build one and inspect its registered tools/resources/prompts
    without actually starting a transport loop."""
    server = MCPServer(name="recut", instructions=_INSTRUCTIONS)
    _register_tools(server)
    _register_resources(server)
    _register_prompts(server)
    return server


def run_stdio_server() -> None:
    """Registers tools.py's tool surface + resources.py's resources on a
    stdio MCP server. Entry point for local mode."""
    build_server().run(transport="stdio")


def build_http_server(*, host: str, port: int) -> MCPServer:
    """Constructs (but does not run) an OAuth-protected MCPServer for the
    Streamable HTTP transport (Unit 4.7). Split out from run_http_server()
    for the same reason as build_server()/run_stdio_server().

    Raises MissingAuthCredentialsError if RECUT_MCP_AUTH_USERNAME/
    RECUT_MCP_AUTH_PASSWORD aren't configured - fails loudly at start time
    rather than falling back to an insecure default (see recut_mcp/auth.py).
    """
    settings = load_settings()
    if not settings.mcp_auth_username or not settings.mcp_auth_password:
        raise MissingAuthCredentialsError(
            "hosted HTTP mode requires RECUT_MCP_AUTH_USERNAME and RECUT_MCP_AUTH_PASSWORD "
            "to be set - refusing to start with no operator credential configured."
        )

    server_url = f"http://{host}:{port}"
    provider = RecutOAuthProvider(
        username=settings.mcp_auth_username,
        password=settings.mcp_auth_password,
        scope=settings.mcp_oauth_scope,
        login_url=f"{server_url}/login",
        server_url=server_url,
    )
    _set_active_provider(provider)

    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(server_url),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=[settings.mcp_oauth_scope],
            default_scopes=[settings.mcp_oauth_scope],
        ),
        required_scopes=[settings.mcp_oauth_scope],
        resource_server_url=None,  # combined AS+RS ("legacy") mode - see recut_mcp/auth.py
    )

    server = MCPServer(
        name="recut",
        instructions=_INSTRUCTIONS,
        auth_server_provider=provider,
        auth=auth_settings,
    )
    _register_tools(server)
    _register_resources(server)
    _register_prompts(server)

    @server.custom_route("/login", methods=["GET"])
    async def login_page_handler(request: Request) -> Response:
        state = request.query_params.get("state")
        if not state:
            raise HTTPException(400, "missing state parameter")
        return await provider.get_login_page(state)

    @server.custom_route("/login/callback", methods=["POST"])
    async def login_callback_handler(request: Request) -> Response:
        return await provider.handle_login_callback(request)

    return server


def run_http_server(*, host: str, port: int) -> None:
    """Streamable HTTP + OAuth 2.1 (Unit 4.7). The same tool surface
    verified working over stdio (Unit 4.6), now behind a real OAuth 2.1
    authorization-code+PKCE flow - see recut_mcp/auth.py for the provider."""
    build_http_server(host=host, port=port).run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    run_stdio_server()
