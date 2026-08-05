"""
Unit 4.1 done criteria (test-client variant): POST /analyze enqueues and
returns a job_id immediately; GET /jobs/{job_id} polls status. Uses
task_always_eager (Settings default - see common/config.py) so the
Celery task actually runs synchronously within the request-response cycle
in this test, without a real worker process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


def test_analyze_returns_job_id_immediately(fake_redis_server) -> None:
    client = TestClient(create_app())
    response = client.post("/analyze", json={"source": str(FIXTURE), "depth": "fast"})
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_get_job_for_unknown_job_id_is_404(fake_redis_server) -> None:
    client = TestClient(create_app())
    response = client.get("/jobs/nonexistent")
    assert response.status_code == 404


def test_analyze_url_source_without_rights_attestation_is_rejected(fake_redis_server) -> None:
    client = TestClient(create_app())
    response = client.post("/analyze", json={"source": "https://example.com/video.mp4", "depth": "fast"})
    assert response.status_code == 400
    assert "rights_attestation" in response.json()["detail"]


@pytest.mark.slow
def test_analyze_then_poll_job_reaches_done_with_real_trace(fake_redis_server) -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    client = TestClient(create_app())
    response = client.post("/analyze", json={"source": str(FIXTURE), "depth": "fast"})
    job_id = response.json()["job_id"]

    # task_always_eager means the task already ran synchronously by the
    # time .delay() returned above - no actual polling loop needed here,
    # but hitting the endpoint once still exercises the real poll path.
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done"
    assert Path(job["result_refs"]["trace_path"]).exists()
