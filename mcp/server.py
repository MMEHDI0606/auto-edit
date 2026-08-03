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
"""

from __future__ import annotations


def run_stdio_server() -> None:
    """Registers tools.py's tool surface + resources.py's resources on a
    stdio MCP server. Entry point for local mode."""
    raise NotImplementedError


def run_http_server(*, host: str, port: int) -> None:
    """Streamable HTTP + OAuth 2.1. Deferred - see module docstring."""
    raise NotImplementedError
