"""
Structured logging setup, shared by CLI, API workers, and MCP server.

Contract: every log line touching a specific job must include `job_id` and
`source_hash` (when known) so that logs, cached traces, and render reports
can be correlated without grepping. Call `get_logger(__name__).bind(job_id=...)`
- do not reach for the stdlib `logging` module directly in new code.
"""

from __future__ import annotations

import logging
import sys

import structlog

_CONFIGURED = False


def _configure_once() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if sys.stdout.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Returns a structlog bound logger. Call `.bind(job_id=..., source_hash=...)`
    on the result at the point a job's identity becomes known, per the
    module contract above."""
    _configure_once()
    return structlog.get_logger(name)
