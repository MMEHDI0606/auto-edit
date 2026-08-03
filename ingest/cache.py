"""
L0 - content-hash cache for normalized video + derived artifacts.

Rationale (spec sec 2.3): the same viral video should be analyzed once
across all users. This is the single biggest cost saver in the system.

DESIGN ADDITION not in the original spec (see DESIGN_NOTES.md, "Cache
takedown gap"): a shared, indefinitely-retained cache of third-party video
content is a rights-management liability the spec's own sec 8.1 legal
analysis doesn't fully close the loop on. This module owns the takedown
path - see `purge()` below. Do not ship the cache without it.

Phase 1 scope (Unit 1.2): filesystem-backed store only. The Postgres-backed
version implied by spec sec 10 waits until Phase 4/5 has an API layer to
back it - a filesystem cache is the right scope for a CLI-only Phase 1.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from common.config import load_settings
from common.types import ContentHash

_CHUNK_SIZE = 1024 * 1024  # 1MB - avoid loading a full video into memory


@dataclass
class CacheEntry:
    content_hash: ContentHash
    normalized_video_path: Path
    wav_path: Path
    probe_json_path: Path
    trace_path: Path | None  # populated once L1 has run


def _cache_dir(content_hash: ContentHash) -> Path:
    return Path(load_settings().cache_root) / content_hash


def hash_file(path: Path) -> ContentHash:
    """SHA256 of the *normalized* video bytes (not the source URL, not the
    original upload) - two different uploads of the same underlying video
    must collide after normalization even if container/bitrate differ."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            digest.update(chunk)
    return ContentHash(digest.hexdigest())


def get(content_hash: ContentHash) -> CacheEntry | None:
    cache_dir = _cache_dir(content_hash)
    norm_path = cache_dir / "norm.mp4"
    if not norm_path.exists():
        return None
    trace_path = cache_dir / "trace.json"
    return CacheEntry(
        content_hash=content_hash,
        normalized_video_path=norm_path,
        wav_path=cache_dir / "norm.wav",
        probe_json_path=cache_dir / "probe.json",
        trace_path=trace_path if trace_path.exists() else None,
    )


def put(content_hash: ContentHash, entry: CacheEntry) -> None:
    """Copies whichever of entry's artifacts exist into the cache directory
    for this hash. Safe to call incrementally (e.g. once right after
    normalize(), again later once trace.json exists) - existing files at
    the destination are left untouched if the source is already the
    destination (avoids copying a file onto itself)."""
    cache_dir = _cache_dir(content_hash)
    cache_dir.mkdir(parents=True, exist_ok=True)

    named_sources = [
        (entry.normalized_video_path, "norm.mp4"),
        (entry.wav_path, "norm.wav"),
        (entry.probe_json_path, "probe.json"),
    ]
    if entry.trace_path is not None:
        named_sources.append((entry.trace_path, "trace.json"))

    for src, name in named_sources:
        if src is None or not src.exists():
            continue
        dest = cache_dir / name
        if src.resolve() == dest.resolve():
            continue
        shutil.copy2(src, dest)


def write_probe_json(content_hash: ContentHash, probe_dict: dict) -> Path:
    """Convenience used by the CLI (Unit 1.18): normalize.probe() returns a
    plain dict, not a file - this persists it into the cache dir so a
    subsequent get() has a real probe_json_path to hand back."""
    cache_dir = _cache_dir(content_hash)
    cache_dir.mkdir(parents=True, exist_ok=True)
    probe_path = cache_dir / "probe.json"
    probe_path.write_text(json.dumps(probe_dict, indent=2))
    return probe_path


def purge(content_hash: ContentHash, *, reason: str) -> None:
    """Delete every cached artifact (normalized video, WAV, trace, any
    derived templates that embed the source hash) for a given content hash.

    This is the takedown / GDPR-deletion / rights-holder-request path.
    Must be callable by an operator without a code deploy (wire this to an
    admin CLI or API endpoint in Phase 4/5 - see BUILD_ORDER.md). Log
    `reason` for audit purposes; do not log the content itself.

    DEFERRED per INSTRUCTIONS.md Unit 1.2: signature exists now so no
    call site needs retrofitting, but real deletion logic + admin trigger
    isn't needed until real user/rights-holder data exists (Phase 5).
    """
    raise NotImplementedError
