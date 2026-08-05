"""
Unit 4.6 - recut_mcp/server.py: registers every tool/resource/prompt on
the real official `mcp` SDK's MCPServer. The unit's own done criterion
("connect a real MCP client - Claude Code, Claude Desktop, or Cursor - and
drive the full flow through natural conversation") is a human dogfood
session, not something an automated test can perform - what IS verified
here is that the real SDK's registration and dispatch machinery actually
works against this project's real tools/resources/prompts: every tool
call, resource read, and prompt fetch goes through the SDK's own
call_tool()/read_resource()/get_prompt(), the same code path a real
client (Claude Desktop, Cursor, Claude Code) drives.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from recut_mcp.resources import PROMPT_NAMES, load_prompt
from recut_mcp.server import _TOOL_NAMES, build_server


def _run(coro):
    return asyncio.run(coro)


def test_build_server_registers_every_tool() -> None:
    server = build_server()
    tools = _run(server.list_tools())
    assert {t.name for t in tools} == set(_TOOL_NAMES)


def test_build_server_registers_every_resource_template() -> None:
    server = build_server()
    templates = _run(server.list_resource_templates())
    assert {t.uri_template for t in templates} == {
        "recut://trace/{job_id}",
        "recut://template/{template_id}",
        "recut://render/{job_id}",
    }


def test_build_server_registers_every_prompt() -> None:
    server = build_server()
    prompts = _run(server.list_prompts())
    assert {p.name for p in prompts} == set(PROMPT_NAMES)


@pytest.mark.parametrize("prompt_name", PROMPT_NAMES)
def test_get_prompt_returns_the_real_authored_text(prompt_name: str) -> None:
    server = build_server()
    result = _run(server.get_prompt(prompt_name))
    returned_text = result.messages[0].content.text
    assert returned_text == load_prompt(prompt_name)


def test_call_tool_search_library_end_to_end_through_real_sdk(fake_redis_server) -> None:
    """Exercises the full real dispatch path: MCPServer.call_tool() ->
    the SDK's own tool manager -> recut_mcp.tools.search_library() ->
    api.store.TemplateStore - against fakeredis, no real Redis needed."""
    server = build_server()
    result = _run(server.call_tool("search_library", {"query": "anything"}))
    assert result.is_error is False
    assert result.structured_content == {"result": []}


def test_read_resource_template_dispatches_to_real_handler(fake_redis_server) -> None:
    from api.store import TemplateStore
    from schemas.models import AudioRef, Template

    template = Template(source_trace_hash="deadbeef", source_fps=30, slots=[], audio_ref=AudioRef())
    template_id = TemplateStore().create(template)

    contents = _run(server_read_resource_contents(f"recut://template/{template_id}"))
    assert json.loads(contents)["source_trace_hash"] == "deadbeef"


async def server_read_resource_contents(uri: str) -> bytes:
    server = build_server()
    results = list(await server.read_resource(uri))
    assert len(results) == 1
    return results[0].content
