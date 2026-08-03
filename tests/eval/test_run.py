"""
eval/run.py's "nothing to evaluate" path - the actual Phase 1 gate run
(>=20 real annotated videos) is blocked per eval/golden/NEEDS_INPUT.md,
but the harness itself must fail predictably (exit 2, clear message) when
pointed at a golden-set directory with no usable video, not crash or
silently report a false "0 regressions" success.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def test_run_exits_2_when_no_annotated_videos_found(tmp_path) -> None:
    empty_golden_dir = tmp_path / "golden"
    empty_golden_dir.mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "eval.run", "--golden-dir", str(empty_golden_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )

    assert result.returncode == 2
    assert "No annotated golden-set videos found" in result.stderr


def test_run_exits_2_when_annotations_exist_but_no_source_media(tmp_path) -> None:
    golden_dir = tmp_path / "golden"
    video_dir = golden_dir / "video_1"
    video_dir.mkdir(parents=True)
    (video_dir / "annotations.json").write_text('{"cuts": [], "text_layers": []}')
    # deliberately no source.mp4

    result = subprocess.run(
        [sys.executable, "-m", "eval.run", "--golden-dir", str(golden_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )

    assert result.returncode == 2
    assert "no source.mp4 present locally" in result.stderr
