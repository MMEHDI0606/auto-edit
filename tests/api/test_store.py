"""
Unit 4.1 - api/store.py's Redis-backed stores, exercised against
fakeredis (see conftest.py's fake_redis_server fixture) rather than a
real Redis server.
"""

from __future__ import annotations

import pytest

from api.store import JobStore, TemplateStore
from schemas.models import AudioRef, Template


def test_job_store_create_starts_pending(fake_redis_server) -> None:
    store = JobStore()
    job_id = store.create()
    job = store.get(job_id)
    assert job == {"status": "pending", "progress": 0.0, "stage": None, "error": None, "result_refs": None}


def test_job_store_update_merges_fields(fake_redis_server) -> None:
    store = JobStore()
    job_id = store.create()
    store.update(job_id, status="running", progress=0.3)
    job = store.get(job_id)
    assert job["status"] == "running"
    assert job["progress"] == 0.3
    assert job["stage"] is None  # untouched fields survive the merge


def test_job_store_mark_running_then_done(fake_redis_server) -> None:
    store = JobStore()
    job_id = store.create()

    store.mark_running(job_id, stage="normalize", progress=0.2)
    assert store.get(job_id)["status"] == "running"
    assert store.get(job_id)["stage"] == "normalize"

    store.mark_done(job_id, result_refs={"trace_path": "/tmp/trace.json"})
    job = store.get(job_id)
    assert job["status"] == "done"
    assert job["progress"] == 1.0
    assert job["result_refs"] == {"trace_path": "/tmp/trace.json"}


def test_job_store_mark_error(fake_redis_server) -> None:
    store = JobStore()
    job_id = store.create()
    store.mark_error(job_id, error="ffmpeg exploded")
    assert store.get(job_id) == {
        "status": "error",
        "progress": 0.0,
        "stage": None,
        "error": "ffmpeg exploded",
        "result_refs": None,
    }


def test_job_store_get_unknown_job_raises(fake_redis_server) -> None:
    store = JobStore()
    with pytest.raises(KeyError):
        store.get("nonexistent")


def test_job_store_idempotency_key_round_trip(fake_redis_server) -> None:
    store = JobStore()
    assert store.get_job_for_idempotency_key("key1") is None

    store.set_idempotency_key("key1", "job-abc")
    assert store.get_job_for_idempotency_key("key1") == "job-abc"


def test_two_job_store_instances_share_state_via_fake_server(fake_redis_server) -> None:
    """Confirms the conftest fixture actually gives independently-
    constructed store instances a shared backend - this is what makes
    testing a Celery task (which builds its own JobStore()) against the
    same job the test created possible at all."""
    store_a = JobStore()
    job_id = store_a.create()

    store_b = JobStore()
    assert store_b.get(job_id)["status"] == "pending"


def test_template_store_round_trip(fake_redis_server) -> None:
    template = Template(source_trace_hash="deadbeef", source_fps=30, slots=[], audio_ref=AudioRef())
    store = TemplateStore()

    template_id = store.create(template)
    # create() syncs Template.template_id to the generated store key (Unit
    # 4.3b) - the round-tripped object differs from the pre-persist input
    # by exactly that one field.
    assert store.get(template_id) == template.model_copy(update={"template_id": template_id})


def test_template_store_get_unknown_id_raises(fake_redis_server) -> None:
    with pytest.raises(KeyError):
        TemplateStore().get("nonexistent")
