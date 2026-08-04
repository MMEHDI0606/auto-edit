"""
Shared render-report helper (Unit 2.8) so every RenderEngine formats
RenderReport.approximations entries the same way regardless of which
engine produced them - a downstream consumer (MCP tool response, eventual
UI) shouldn't need per-engine special-casing to parse or display these.

Convention: always "{slot_id}: {reason}" - a plain, human-readable,
greppable/diffable string, not a structured object (spec sec 7.3 frames
this as something a user reads directly, not machine-parsed metadata).
"""

from __future__ import annotations


def format_approximation(slot_id: str, reason: str) -> str:
    return f"{slot_id}: {reason}"


def add_approximation(approximations: list[str], slot_id: str, reason: str) -> None:
    approximations.append(format_approximation(slot_id, reason))
