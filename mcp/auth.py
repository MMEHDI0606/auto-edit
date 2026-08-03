"""
OAuth 2.1 for the hosted HTTP transport (spec sec 9.2). STUB ONLY - local
stdio mode (the v1 default, see DESIGN_NOTES.md "Local-first default")
needs no auth at all. Implement this only when hosted mode is actually
being built (BUILD_ORDER.md Phase 4b).
"""

from __future__ import annotations


def verify_token(token: str) -> dict:
    """Returns the authenticated principal's claims, or raises."""
    raise NotImplementedError
