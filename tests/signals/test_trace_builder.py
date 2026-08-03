"""
Unit 1.17 done criteria: build_trace() run against a real video (the
synthetic_clip.mp4 fixture, standing in for the golden set until real
footage is supplied per eval/golden/NEEDS_INPUT.md) produces a valid
EditTrace with no crash - this is the first point the full L1 pipeline
runs end to end.

Genuinely slow (whisper + demucs + full CV pipeline decode/re-encode) -
this is the integration smoke test, not a fast unit test; give it a
generous timeout when running.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from ingest.normalize import normalize, probe
from schemas.models import EditTrace
from signals.trace_builder import build_trace

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


@pytest.mark.slow
def test_build_trace_end_to_end_on_synthetic_clip() -> None:
    if not FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = Path(tmp_dir)
        result = normalize(FIXTURE, out_dir, fps=30, width=1080, height=1920, crf=18)
        probe_dict = probe(result.normalized_path)

        trace = build_trace(result.normalized_path, result.wav_path, probe_dict)

        # Re-validates the object through the schema, matching the done
        # criteria's own phrasing ("EditTrace.model_validate(...) doesn't raise").
        try:
            EditTrace.model_validate(trace.model_dump())
        except ValidationError as exc:  # pragma: no cover - failure path
            pytest.fail(f"build_trace produced an invalid EditTrace: {exc}")

        assert trace.source.duration_s > 0
        assert len(trace.shots) == 3  # 2 known hard cuts -> 3 shots, per synthetic_clip.meta.json
        assert trace.shots[0].t_in == 0.0
        assert trace.shots[-1].t_out == pytest.approx(trace.source.duration_s, abs=0.05)
        # Known "HOOK TEXT" overlay should produce at least one layer.
        assert len(trace.text_layers) >= 1
