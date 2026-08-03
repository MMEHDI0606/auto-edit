"""
FastAPI app. Thin HTTP surface over the same job/pipeline primitives the
MCP tool layer (mcp/tools.py) calls - both are clients of this module's
job-orchestration functions, neither contains business logic.

Also the enforcement point for the "user-provided files and
user-authorised pulls" rights posture (spec sec 8.1): URL-based analyze
requests must carry a rights attestation from the caller before
ingest.downloader.fetch is ever invoked - that check belongs here, not in
ingest/ (ingest/ trusts its caller; api/ is the caller that must not trust
its own caller blindly).
"""

from __future__ import annotations


def create_app():
    raise NotImplementedError
