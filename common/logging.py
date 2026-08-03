"""
Structured logging setup, shared by CLI, API workers, and MCP server.

Contract: every log line touching a specific job must include `job_id` and
`source_hash` (when known) so that logs, cached traces, and render reports
can be correlated without grepping. Use `get_logger(__name__).bind(job_id=...)`
(structlog) once the dependency is added in Phase 0 - do not reach for the
stdlib `logging` module directly in new code.
"""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Placeholder returning a stdlib logger. Swap for structlog in Phase 0
    without changing call sites (keep the `get_logger(name)` signature)."""
    return logging.getLogger(name)
