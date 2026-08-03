"""
Unit 1.18 done criteria: `python -m cli.analyze <mp4> --out trace.json`
runs to completion on a real file and produces a valid, readable JSON
file. Running it a second time on the same file completes near-instantly
(cache hit, Unit 1.2) rather than re-running ffmpeg/whisper/demucs.

Genuinely slow on the first invocation (the whole pipeline) - marked
`slow` like the trace_builder integration test it wraps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synthetic_clip.mp4"


@pytest.mark.slow
def test_cli_produces_trace_and_second_run_is_a_fast_cache_hit(tmp_path) -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    out_path = tmp_path / "trace.json"
    env = {**os.environ, "RECUT_CACHE_ROOT": str(tmp_path / "cache")}

    first = subprocess.run(
        [sys.executable, "-m", "cli.analyze", str(FIXTURE), "--out", str(out_path)],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )
    assert first.returncode == 0, first.stderr
    assert out_path.exists()

    trace = json.loads(out_path.read_text())
    assert len(trace["shots"]) == 3
    assert "cache hit" not in first.stderr

    start = time.time()
    second = subprocess.run(
        [sys.executable, "-m", "cli.analyze", str(FIXTURE), "--out", str(out_path)],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )
    elapsed = time.time() - start

    assert second.returncode == 0, second.stderr
    assert "cache hit" in second.stderr
    assert elapsed < 15, f"cache hit took {elapsed}s - ffmpeg/whisper/demucs likely re-ran"

    second_trace = json.loads(out_path.read_text())
    assert second_trace == trace
