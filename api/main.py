"""
FastAPI app. Thin HTTP surface over the same job/pipeline primitives the
MCP tool layer (recut_mcp/tools.py) calls - both are clients of this module's
job-orchestration functions, neither contains business logic.

Also the enforcement point for the "user-provided files and
user-authorised pulls" rights posture (spec sec 8.1): URL-based analyze
requests must carry a rights attestation from the caller before
ingest.downloader.fetch is ever invoked - that check belongs here, not in
ingest/ (ingest/ trusts its caller; api/ is the caller that must not trust
its own caller blindly).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from api.store import JobStore
from api.workers import analyze_video_task

_URL_PREFIXES = ("http://", "https://")


class AnalyzeRequest(BaseModel):
    source: str
    depth: str = "full"
    # Required (True) for URL sources - see module docstring's rights-
    # posture note. Local file paths need no attestation: the caller
    # already has the bytes, there's nothing to pull on their behalf.
    rights_attestation: bool = False


def create_app() -> FastAPI:
    app = FastAPI(title="RECUT API")
    job_store = JobStore()

    @app.post("/analyze")
    def analyze(request: AnalyzeRequest) -> dict:
        if request.source.startswith(_URL_PREFIXES) and not request.rights_attestation:
            raise HTTPException(
                status_code=400,
                detail=(
                    "URL-based analyze requires rights_attestation=true - you must have the "
                    "rights to use this video. See DESIGN_NOTES.md's 'Legal posture' section. "
                    "Local file uploads need no attestation."
                ),
            )

        job_id = job_store.create()
        analyze_video_task.delay(job_id, request.source, request.depth)
        return {"job_id": job_id}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        try:
            return job_store.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"no job {job_id!r}")

    return app
