"""
Unit 1.1b done criteria.

The "fetch a known-stable public URL succeeds" check is deliberately NOT run
by default - it requires a real network call against a third-party
platform, and per RECUT_SPEC.md sec 8.1 / DESIGN_NOTES.md "Legal posture"
this module must only ever be invoked for a URL the calling user asserts
they have rights to pull. Set RECUT_TEST_YTDLP_URL to a URL you're
authorized to fetch to opt into that check locally; CI does not set it.

The "broken/unsupported URL raises UnsupportedSourceError, not a raw
yt-dlp exception" check runs unconditionally and needs no real download -
an unresolvable/malformed URL is enough to exercise the wrapping behavior.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ingest.downloader import UnsupportedSourceError, fetch, pin_yt_dlp_version


def test_pin_yt_dlp_version_matches_pyproject() -> None:
    pyproject = (Path(__file__).parent.parent.parent / "pyproject.toml").read_text()
    assert f'yt-dlp=={pin_yt_dlp_version()}' in pyproject


def test_fetch_wraps_unsupported_url_as_unsupported_source_error(tmp_path) -> None:
    with pytest.raises(UnsupportedSourceError):
        fetch("https://this-domain-does-not-exist.invalid/not-a-video", tmp_path)


@pytest.mark.skipif(
    "RECUT_TEST_YTDLP_URL" not in os.environ,
    reason="set RECUT_TEST_YTDLP_URL to a URL you're authorized to fetch to run this",
)
def test_fetch_real_url_end_to_end(tmp_path) -> None:
    result = fetch(os.environ["RECUT_TEST_YTDLP_URL"], tmp_path)
    assert result.local_path.exists()
    assert result.local_path.stat().st_size > 0
