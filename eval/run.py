"""
Runs the full golden-set evaluation and prints/persists a report. This is
the REGRESSION GATE (spec sec 12): no model or dependency upgrade (yt-dlp,
PySceneDetect, a pinned VLM model_id, etc) merges without this being
re-run and compared against the last known-good numbers.

Usage:
    python -m eval.run --golden-dir eval/golden --out eval/reports/latest.json

Exit codes:
    0  ran, no baseline regression (or no baseline yet - this run BECOMES
       the baseline)
    1  ran, at least one metric regressed beyond its tolerance band vs.
       eval/reports/baseline.json
    2  nothing to evaluate - no annotated golden-set video had a local
       source file available (see eval/golden/NEEDS_INPUT.md). This is
       NOT the same as "0 regressions" and must not be conflated with a
       passing run.

Convention for a golden video directory (eval/golden/<video_id>/):
    annotations.json   hand-labeled ground truth (required)
    source.mp4         the actual media, local-only, NEVER committed to
                        git (see eval/golden/.gitkeep) - if absent, that
                        video is skipped with a warning, not treated as a
                        failure of the pipeline itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from eval import metrics as metrics_mod
from ingest.normalize import normalize, probe
from signals.trace_builder import build_trace

# Tolerance band per metric - a regression is "dropped by more than this
# vs. the stored baseline," not "isn't perfect." Percentage-point bands
# per INSTRUCTIONS.md Unit 1.19 ("e.g. 2 percentage points").
REGRESSION_TOLERANCE = {
    "cut_boundary_f1": 0.02,
    "text_layer_timing_iou": 0.02,
}

PHASE_1_GATE = {
    "min_videos": 20,
    "min_cut_boundary_f1": 0.90,
    "min_text_layer_timing_iou": 0.85,
}


def _discover_golden_videos(golden_dir: Path) -> list[Path]:
    if not golden_dir.exists():
        return []
    return sorted(p for p in golden_dir.iterdir() if p.is_dir() and (p / "annotations.json").exists())


def _evaluate_one(video_dir: Path) -> dict | None:
    annotations = json.loads((video_dir / "annotations.json").read_text())
    source_path = video_dir / "source.mp4"
    if not source_path.exists():
        return None

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        norm_result = normalize(source_path, out_dir, fps=30, width=1080, height=1920, crf=18)
        probe_dict = probe(norm_result.normalized_path)
        trace = build_trace(norm_result.normalized_path, norm_result.wav_path, probe_dict)

    fps = trace.source.fps
    predicted_cuts = [shot.t_in for shot in trace.shots[1:]]
    ground_truth_cuts = [c["t"] for c in annotations.get("cuts", [])]
    cut_metrics = metrics_mod.cut_boundary_f1(predicted_cuts, ground_truth_cuts, tolerance_frames=2, fps=fps)

    predicted_layers = [
        {"string": layer.string, "t_in": layer.t_in, "t_out": layer.t_out} for layer in trace.text_layers
    ]
    ground_truth_layers = annotations.get("text_layers", [])
    text_iou = metrics_mod.text_layer_timing_iou(predicted_layers, ground_truth_layers)
    text_cer = metrics_mod.text_layer_cer(predicted_layers, ground_truth_layers)

    return {
        "video_id": video_dir.name,
        "cut_boundary_f1": cut_metrics,
        "text_layer_timing_iou": text_iou,
        "text_layer_cer": text_cer,
    }


def _check_regression(aggregate: dict, baseline_path: Path) -> bool:
    """Returns True if a regression was found (and printed)."""
    if not baseline_path.exists():
        print(f"no baseline at {baseline_path} - writing this run as the new baseline", file=sys.stderr)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps({"aggregate": aggregate}, indent=2))
        return False

    baseline = json.loads(baseline_path.read_text())["aggregate"]
    regressed = False
    for metric, tolerance in REGRESSION_TOLERANCE.items():
        if metric not in aggregate or metric not in baseline:
            continue
        if aggregate[metric] < baseline[metric] - tolerance:
            print(f"REGRESSION: {metric} dropped from {baseline[metric]:.4f} to {aggregate[metric]:.4f}", file=sys.stderr)
            regressed = True
    return regressed


def main() -> None:
    parser = argparse.ArgumentParser(description="RECUT golden-set evaluation (Phase 1 regression gate)")
    parser.add_argument("--golden-dir", default="eval/golden")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    golden_dir = Path(args.golden_dir)
    video_dirs = _discover_golden_videos(golden_dir)

    if not video_dirs:
        print(
            f"No annotated golden-set videos found under {golden_dir} "
            "(each needs its own <video_id>/annotations.json + source.mp4). "
            "See eval/golden/NEEDS_INPUT.md - the Phase 1 gate "
            f"(>={PHASE_1_GATE['min_videos']} real videos, "
            f"cut-boundary F1 >= {PHASE_1_GATE['min_cut_boundary_f1']}, "
            f"text-layer IoU >= {PHASE_1_GATE['min_text_layer_timing_iou']}) "
            "cannot be evaluated without real footage.",
            file=sys.stderr,
        )
        sys.exit(2)

    reports = []
    for video_dir in video_dirs:
        result = _evaluate_one(video_dir)
        if result is None:
            print(f"skipping {video_dir.name}: no source.mp4 present locally", file=sys.stderr)
            continue
        reports.append(result)

    if not reports:
        print("no golden videos had a local source file to evaluate against", file=sys.stderr)
        sys.exit(2)

    aggregate = {
        "cut_boundary_f1": sum(r["cut_boundary_f1"]["f1"] for r in reports) / len(reports),
        "text_layer_timing_iou": sum(r["text_layer_timing_iou"] for r in reports) / len(reports),
        "n_videos": len(reports),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    print(json.dumps(aggregate, indent=2))
    for r in reports:
        print(f"  {r['video_id']}: F1={r['cut_boundary_f1']['f1']:.3f} text_iou={r['text_layer_timing_iou']:.3f}")

    out_path = Path(args.out) if args.out else Path("eval/reports") / f"{aggregate['timestamp'].replace(':', '-')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"aggregate": aggregate, "per_video": reports}, indent=2))

    regressed = _check_regression(aggregate, Path("eval/reports/baseline.json"))

    gate_met = (
        aggregate["n_videos"] >= PHASE_1_GATE["min_videos"]
        and aggregate["cut_boundary_f1"] >= PHASE_1_GATE["min_cut_boundary_f1"]
        and aggregate["text_layer_timing_iou"] >= PHASE_1_GATE["min_text_layer_timing_iou"]
    )
    if not gate_met:
        print(
            "Phase 1 gate NOT met "
            f"(need >={PHASE_1_GATE['min_videos']} videos with F1>={PHASE_1_GATE['min_cut_boundary_f1']} "
            f"and text_iou>={PHASE_1_GATE['min_text_layer_timing_iou']}; "
            f"have n_videos={aggregate['n_videos']}, F1={aggregate['cut_boundary_f1']:.3f}, "
            f"text_iou={aggregate['text_layer_timing_iou']:.3f}).",
            file=sys.stderr,
        )

    if regressed:
        sys.exit(1)


if __name__ == "__main__":
    main()
