"""
L0 - source acquisition.

Wraps yt-dlp for URL sources. Uploaded files bypass this module entirely
and go straight to normalize.py - see DESIGN_NOTES.md "Ingest policy":
upload is the first-class, always-works path; URL download is optional
and allowed to fail without failing the job.

Do NOT add bulk/scheduled crawling here. This module fetches exactly one
user-requested URL per call. See DESIGN_NOTES.md "Legal posture" for why
that boundary is load-bearing, not just tidy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class UnsupportedSourceError(Exception):
    """Raised when a URL's platform extractor is unavailable or blocked
    (e.g. TikTok datacenter-IP block, IG auth wall). Caller must treat this
    as recoverable - see ingest policy: never let a download failure kill
    a job when the user could instead be asked to upload the file."""


@dataclass
class DownloadResult:
    local_path: Path
    platform: str
    source_url: str
    extractor_used: str


def fetch(url: str, dest_dir: Path) -> DownloadResult:
    """Download `url` into `dest_dir` via yt-dlp.

    Contract:
    - Must only be called for a URL the calling user asserts they have
      rights to pull (enforced at the API layer, not here - see api/main.py).
    - Must raise UnsupportedSourceError rather than a raw yt-dlp exception
      so callers have one error type to branch on.
    - Must NOT retry indefinitely; a bounded retry (e.g. 2 attempts) with
      backoff, then raise.
    """
    raise NotImplementedError


def pin_yt_dlp_version() -> str:
    """Returns the currently pinned yt-dlp version string.

    yt-dlp extractors break weekly (spec sec 8.2). Pin the version in
    pyproject.toml, but also record it here per-job (into EvidenceMeta /
    job metadata) so a regression can be bisected to a yt-dlp upgrade.
    """
    raise NotImplementedError
