"""
Runs the full golden-set evaluation and prints/persists a report. This is
the REGRESSION GATE (spec sec 12): no model or dependency upgrade (yt-dlp,
PySceneDetect, a pinned VLM model_id, etc) merges without this being
re-run and compared against the last known-good numbers.

Usage (once implemented):
    python -m eval.run --golden-dir eval/golden --out eval/reports/latest.json

Should exit non-zero if any metric regresses beyond a tolerance band
(define the band per metric here, not scattered across CI config) so it
can be wired into CI as a hard gate in Phase 1.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
