"""
L0 - content-hash cache for normalized video + derived artifacts.

Rationale (spec sec 2.3): the same viral video should be analyzed once
across all users. This is the single biggest cost saver in the system.

DESIGN ADDITION not in the original spec (see DESIGN_NOTES.md, "Cache
takedown gap"): a shared, indefinitely-retained cache of third-party video
content is a rights-management liability the spec's own sec 8.1 legal
analysis doesn't fully close the loop on. This module owns the takedown
path - see `purge()` below. Do not ship the cache without it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from common.types import ContentHash


@dataclass
class CacheEntry:
    content_hash: ContentHash
    normalized_video_path: Path
    wav_path: Path
    probe_json_path: Path
    trace_path: Path | None  # populated once L1 has run


def hash_file(path: Path) -> ContentHash:
    """SHA256 of the *normalized* video bytes (not the source URL, not the
    original upload) - two different uploads of the same underlying video
    must collide after normalization even if container/bitrate differ."""
    raise NotImplementedError


def get(content_hash: ContentHash) -> CacheEntry | None:
    raise NotImplementedError


def put(content_hash: ContentHash, entry: CacheEntry) -> None:
    raise NotImplementedError


def purge(content_hash: ContentHash, *, reason: str) -> None:
    """Delete every cached artifact (normalized video, WAV, trace, any
    derived templates that embed the source hash) for a given content hash.

    This is the takedown / GDPR-deletion / rights-holder-request path.
    Must be callable by an operator without a code deploy (wire this to an
    admin CLI or API endpoint in Phase 4/5 - see BUILD_ORDER.md). Log
    `reason` for audit purposes; do not log the content itself.
    """
    raise NotImplementedError
