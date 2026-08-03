"""
L6 - MCP resources: recut://trace/{id}, recut://template/{id},
recut://render/{id} (spec sec 9.3). Resources are how large artifacts
(full traces, rendered video) are addressed without going through a tool
call's return payload - a tool returns a resource URI, the agent fetches
the resource only if/when it actually needs the full content.

Also owns the `recreate_this_edit`, `explain_this_edit`,
`find_similar_template` MCP prompts (spec sec 9.3) - these are prompt
TEMPLATES registered with the server, not Python functions; store them as
data (e.g. prompts/*.md) once written, don't inline long prompt strings
into this module.
"""

from __future__ import annotations


def get_resource(uri: str) -> bytes:
    raise NotImplementedError


PROMPT_NAMES = ["recreate_this_edit", "explain_this_edit", "find_similar_template"]
