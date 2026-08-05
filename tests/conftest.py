"""
Every api/ store (JobStore, TemplateStore, ...) builds its own redis-py
client via api.store._default_client() when no client is explicitly
injected - including instances constructed deep inside a Celery task
(api/workers.py), where wiring an injected client through every layer
would be invasive. Patching redis.Redis.from_url itself, process-wide for
the duration of a test, to return a fakeredis client bound to one shared
FakeServer means every store instance created anywhere (app layer, task
layer) transparently shares the same in-memory backend - the real
api/store.py and api/workers.py code paths run completely unmodified,
only the actual network client underneath is swapped for a real
reimplementation of the redis-py wire protocol against memory instead of
an actual Redis server (fakeredis, not a hand-rolled mock).
"""

from __future__ import annotations

import fakeredis
import pytest
import redis


@pytest.fixture()
def fake_redis_server(monkeypatch):
    server = fakeredis.FakeServer()

    def _from_url(url: str, *, decode_responses: bool = False, **kwargs):
        return fakeredis.FakeStrictRedis(server=server, decode_responses=decode_responses)

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(_from_url))
    return server
