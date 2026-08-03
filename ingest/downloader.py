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

import time
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

# Pinned per pyproject.toml Unit 0.1 - keep these in lockstep. Recorded here
# (not just in pyproject.toml) so it can be written into EvidenceMeta /
# job metadata per-job, letting a future regression be bisected to a
# yt-dlp upgrade (spec sec 8.2).
_PINNED_YT_DLP_VERSION = "2026.7.4"

_MAX_ATTEMPTS = 2
_RETRY_BACKOFF_S = 2.0


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


def _download_once(url: str, dest_dir: Path) -> DownloadResult:
    outtmpl = str(dest_dir / "%(id)s.%(ext)s")
    opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        local_path = Path(ydl.prepare_filename(info))
        # merge_output_format can change the on-disk extension after mux -
        # prepare_filename reflects the pre-merge name, so fall back to
        # scanning for the actual produced file if it doesn't exist.
        if not local_path.exists():
            candidates = sorted(dest_dir.glob(f"{info['id']}.*"))
            if not candidates:
                raise UnsupportedSourceError(f"yt-dlp reported success but produced no file for {url!r}")
            local_path = candidates[0]

    return DownloadResult(
        local_path=local_path,
        platform=info.get("extractor_key", "unknown"),
        source_url=url,
        extractor_used=info.get("extractor", "unknown"),
    )


def fetch(url: str, dest_dir: Path) -> DownloadResult:
    """Download `url` into `dest_dir` via yt-dlp.

    Contract:
    - Must only be called for a URL the calling user asserts they have
      rights to pull (enforced at the API layer, not here - see api/main.py).
    - Must raise UnsupportedSourceError rather than a raw yt-dlp exception
      so callers have one error type to branch on.
    - Must NOT retry indefinitely; a bounded retry (2 attempts) with
      backoff, then raise.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return _download_once(url, dest_dir)
        except UnsupportedSourceError:
            raise
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - yt-dlp raises a wide variety of extractor errors
            last_error = exc
        if attempt < _MAX_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_S)
    raise UnsupportedSourceError(f"failed to fetch {url!r} after {_MAX_ATTEMPTS} attempts") from last_error


def pin_yt_dlp_version() -> str:
    """Returns the currently pinned yt-dlp version string.

    yt-dlp extractors break weekly (spec sec 8.2). Pin the version in
    pyproject.toml, but also record it here per-job (into EvidenceMeta /
    job metadata) so a regression can be bisected to a yt-dlp upgrade.
    """
    return _PINNED_YT_DLP_VERSION
