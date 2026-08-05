"""
Redis-backed key-value stores for every persisted L4-L6 artifact: jobs,
compiled templates, registered assets, and bindings. One generic store
class parameterized by key prefix + (de)serializer - avoids reimplementing
the same get/put boilerplate four times for what is, underneath, always
the same shape (id -> JSON blob), while still keeping each artifact type's
own store instance distinctly named and typed at call sites.

Every store accepts an injected redis-py-compatible client so tests can
pass `fakeredis.FakeStrictRedis()` - a real reimplementation of the
redis-py wire protocol against an in-memory store, not a hand-rolled mock -
without needing a real Redis server running.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from typing import Callable, Generic, TypeVar

import redis

from common.config import load_settings
from matcher.probe import AssetFeatures
from schemas.models import BindingSet, Template

T = TypeVar("T")


def _default_client() -> redis.Redis:
    return redis.Redis.from_url(load_settings().redis_url, decode_responses=True)


class RedisJSONStore(Generic[T]):
    """id -> JSON-serialized value, all keys namespaced under
    `recut:{prefix}:`."""

    def __init__(
        self,
        prefix: str,
        *,
        serialize: Callable[[T], str],
        deserialize: Callable[[str], T],
        client: redis.Redis | None = None,
    ) -> None:
        self._prefix = prefix
        self._serialize = serialize
        self._deserialize = deserialize
        self._client = client or _default_client()

    def _key(self, id_: str) -> str:
        return f"recut:{self._prefix}:{id_}"

    def new_id(self) -> str:
        return str(uuid.uuid4())

    def put(self, id_: str, value: T) -> str:
        self._client.set(self._key(id_), self._serialize(value))
        return id_

    def get(self, id_: str) -> T:
        raw = self._client.get(self._key(id_))
        if raw is None:
            raise KeyError(f"no {self._prefix!r} entry with id {id_!r}")
        return self._deserialize(raw)

    def exists(self, id_: str) -> bool:
        return bool(self._client.exists(self._key(id_)))


class JobStore:
    """job_id -> {status, progress, stage, error, result_refs}. The only
    store here whose entries are mutated in place (every other store's
    artifacts are immutable once created) - jobs move through
    pending -> running -> done|error, updated at each pipeline stage
    boundary (Unit 4.1's own requirement)."""

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._jobs: RedisJSONStore[dict] = RedisJSONStore(
            "job", serialize=json.dumps, deserialize=json.loads, client=client
        )
        self._idempotency: RedisJSONStore[str] = RedisJSONStore(
            "idempotency", serialize=lambda v: v, deserialize=lambda v: v, client=client
        )

    def create(self) -> str:
        job_id = self._jobs.new_id()
        self._jobs.put(
            job_id,
            {"status": "pending", "progress": 0.0, "stage": None, "error": None, "result_refs": None},
        )
        return job_id

    def get(self, job_id: str) -> dict:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        data = self._jobs.get(job_id)
        data.update(fields)
        self._jobs.put(job_id, data)

    def mark_running(self, job_id: str, *, stage: str, progress: float) -> None:
        self.update(job_id, status="running", stage=stage, progress=progress)

    def mark_done(self, job_id: str, *, result_refs: dict) -> None:
        self.update(job_id, status="done", stage="done", progress=1.0, result_refs=result_refs)

    def mark_error(self, job_id: str, *, error: str) -> None:
        self.update(job_id, status="error", error=error)

    # --- idempotency (Unit 4.4: render() requires idempotency_key) ---

    def get_job_for_idempotency_key(self, key: str) -> str | None:
        try:
            return self._idempotency.get(key)
        except KeyError:
            return None

    def set_idempotency_key(self, key: str, job_id: str) -> None:
        self._idempotency.put(key, job_id)


class TemplateStore:
    """template_id -> Template. The store-generated id IS the template's
    identity - Template itself carries no id field until Unit 4.3b adds
    one (for adjust_template()'s derived_from lineage); until then, this
    store is the only place a template_id exists."""

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._store: RedisJSONStore[Template] = RedisJSONStore(
            "template",
            serialize=lambda t: t.model_dump_json(),
            deserialize=Template.model_validate_json,
            client=client,
        )

    def create(self, template: Template) -> str:
        template_id = self._store.new_id()
        self._store.put(template_id, template)
        return template_id

    def put(self, template_id: str, template: Template) -> None:
        self._store.put(template_id, template)

    def get(self, template_id: str) -> Template:
        return self._store.get(template_id)


class AssetStore:
    """asset_id -> AssetFeatures. AssetFeatures is a plain dataclass (see
    matcher/probe.py), not a Pydantic model, so it needs its own
    json.dumps/loads-based (de)serializer rather than TemplateStore's
    model_dump_json()/model_validate_json()."""

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._store: RedisJSONStore[AssetFeatures] = RedisJSONStore(
            "asset",
            serialize=lambda a: json.dumps(dataclasses.asdict(a)),
            deserialize=lambda raw: AssetFeatures(**json.loads(raw)),
            client=client,
        )

    def new_id(self) -> str:
        # Exposed (unlike TemplateStore/BindingStore's create()-only
        # pattern) because matcher.probe.extract_asset_features() itself
        # takes asset_id as a parameter - register_assets() (Unit 4.3)
        # needs the id BEFORE feature extraction can even run, not after.
        return self._store.new_id()

    def put(self, asset_id: str, features: AssetFeatures) -> None:
        self._store.put(asset_id, features)

    def create(self, features: AssetFeatures) -> str:
        asset_id = self._store.new_id()
        self._store.put(asset_id, features)
        return asset_id

    def get(self, asset_id: str) -> AssetFeatures:
        return self._store.get(asset_id)


class BindingStore:
    """binding_id -> BindingSet. Also store-generated id as identity, same
    as TemplateStore - BindingSet already carries its OWN binding_id field
    (schemas/models.py), so this store's key and BindingSet.binding_id
    must be kept in sync at write time (create() below does this)."""

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._store: RedisJSONStore[BindingSet] = RedisJSONStore(
            "binding",
            serialize=lambda b: b.model_dump_json(),
            deserialize=BindingSet.model_validate_json,
            client=client,
        )

    def create(self, binding_set: BindingSet) -> str:
        binding_id = self._store.new_id()
        # BindingSet.binding_id must match the store key - construct a new
        # BindingSet carrying the real generated id rather than trusting
        # whatever id the caller happened to set on the object it built.
        binding_set = binding_set.model_copy(update={"binding_id": binding_id})
        self._store.put(binding_id, binding_set)
        return binding_id

    def get(self, binding_id: str) -> BindingSet:
        return self._store.get(binding_id)
