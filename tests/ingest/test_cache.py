"""
Unit 1.2 done criteria (partial - the CLI-level "second run doesn't
re-invoke ffmpeg" check is in tests/test_cli.py per Unit 1.18, since it
needs the full normalize+cache wiring). This file covers cache.py's own
functions in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.config import load_settings
from ingest.cache import CacheEntry, get, hash_file, put


@pytest.fixture()
def cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("RECUT_CACHE_ROOT", str(tmp_path))
    load_settings.cache_clear()
    yield tmp_path
    load_settings.cache_clear()


def test_hash_file_is_deterministic_and_content_sensitive(tmp_path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")
    c = tmp_path / "c.bin"
    c.write_bytes(b"different content")

    assert hash_file(a) == hash_file(b)
    assert hash_file(a) != hash_file(c)


def test_get_returns_none_for_unknown_hash(cache_root) -> None:
    assert get("deadbeef") is None


def test_put_then_get_round_trips(cache_root, tmp_path) -> None:
    src_dir = tmp_path / "job_out"
    src_dir.mkdir()
    norm = src_dir / "norm.mp4"
    wav = src_dir / "norm.wav"
    probe_json = src_dir / "probe.json"
    norm.write_bytes(b"fake video bytes")
    wav.write_bytes(b"fake wav bytes")
    probe_json.write_text("{}")

    entry = CacheEntry(
        content_hash="abc123",
        normalized_video_path=norm,
        wav_path=wav,
        probe_json_path=probe_json,
        trace_path=None,
    )
    put("abc123", entry)

    fetched = get("abc123")
    assert fetched is not None
    assert fetched.normalized_video_path.read_bytes() == b"fake video bytes"
    assert fetched.wav_path.read_bytes() == b"fake wav bytes"
    assert fetched.trace_path is None
