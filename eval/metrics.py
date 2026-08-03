"""
Metrics against the golden set. See RECUT_SPEC.md sec 12 - build this in
Phase 1, not later.

DESIGN ADDITION not explicit in the spec (see DESIGN_NOTES.md "Two-tier
eval"): these functions operate on the golden set (expensive, slow,
real video). A second, faster tier - synthetic fixtures in
eval/fixtures.py - exists for unit-level dev loop (e.g. testing
signals.cuts.reconcile_detectors against a hand-built boundary list without
running PySceneDetect at all). Keep both tiers; the golden set alone is
too slow to run on every commit.
"""

from __future__ import annotations

import difflib


def _match_within_tolerance(
    predicted_cuts_s: list[float], ground_truth_cuts_s: list[float], tolerance_s: float
) -> tuple[int, int, int]:
    """One-to-one greedy matching by nearest time, globally (not first-come-
    first-served by prediction order) - collects every (pred, gt) pair
    within tolerance, sorts by distance, then greedily assigns smallest
    distances first so no prediction "steals" a ground-truth cut a closer
    prediction should have matched. Returns (tp, fp, fn)."""
    candidates = []
    for p_idx, pred_t in enumerate(predicted_cuts_s):
        for g_idx, gt_t in enumerate(ground_truth_cuts_s):
            dist = abs(pred_t - gt_t)
            if dist <= tolerance_s:
                candidates.append((dist, p_idx, g_idx))
    candidates.sort(key=lambda c: c[0])

    used_pred: set[int] = set()
    used_gt: set[int] = set()
    for _dist, p_idx, g_idx in candidates:
        if p_idx in used_pred or g_idx in used_gt:
            continue
        used_pred.add(p_idx)
        used_gt.add(g_idx)

    tp = len(used_pred)
    fp = len(predicted_cuts_s) - tp
    fn = len(ground_truth_cuts_s) - len(used_gt)
    return tp, fp, fn


def cut_boundary_f1(
    predicted_cuts_s: list[float], ground_truth_cuts_s: list[float], *, tolerance_frames: int, fps: int
) -> dict:
    """Precision/recall/F1 @ +/- tolerance_frames. Target from spec sec 11
    Phase 1 gate: >=90% F1 within +/-2 frames."""
    tolerance_s = tolerance_frames / fps
    tp, fp, fn = _match_within_tolerance(predicted_cuts_s, ground_truth_cuts_s, tolerance_s)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def transition_type_accuracy(predicted: list[str], ground_truth: list[str]) -> float:
    """Accuracy over MATCHED true-positive pairs only - a cut that wasn't
    detected at all has no "correct type" to score, so callers must
    already have paired predicted[i] with ground_truth[i] (e.g. only the
    boundaries cut_boundary_f1 counted as true positives)."""
    if not predicted:
        return 0.0
    correct = sum(1 for p, g in zip(predicted, ground_truth) if p == g)
    return correct / len(predicted)


def _match_by_string_then_time(
    predicted_layers: list[dict], ground_truth_layers: list[dict]
) -> list[tuple[dict, dict]]:
    """Matches each predicted layer to its best-overlapping ground-truth
    layer BY STRING SIMILARITY FIRST (to avoid matching the wrong layer
    when several appear at similar times), per INSTRUCTIONS.md Unit 1.19."""
    used_gt: set[int] = set()
    pairs = []
    for pred in predicted_layers:
        best_idx, best_sim = None, -1.0
        for idx, gt in enumerate(ground_truth_layers):
            if idx in used_gt:
                continue
            sim = difflib.SequenceMatcher(None, pred["string"], gt["string"]).ratio()
            if sim > best_sim:
                best_sim, best_idx = sim, idx
        if best_idx is None:
            continue
        used_gt.add(best_idx)
        pairs.append((pred, ground_truth_layers[best_idx]))
    return pairs


def _temporal_iou(a_in: float, a_out: float, b_in: float, b_out: float) -> float:
    inter = max(0.0, min(a_out, b_out) - max(a_in, b_in))
    union = max(a_out, b_out) - min(a_in, b_in)
    return inter / union if union > 0 else 0.0


def text_layer_timing_iou(predicted_layers: list[dict], ground_truth_layers: list[dict]) -> float:
    """Target: >=85% (spec sec 11 Phase 1 gate)."""
    pairs = _match_by_string_then_time(predicted_layers, ground_truth_layers)
    if not pairs:
        return 0.0
    ious = [_temporal_iou(p["t_in"], p["t_out"], g["t_in"], g["t_out"]) for p, g in pairs]
    return sum(ious) / len(ious)


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def text_layer_cer(predicted_layers: list[dict], ground_truth_layers: list[dict]) -> float:
    """Character error rate on OCR'd strings vs ground truth - matched the
    same string-similarity-first way as text_layer_timing_iou (a
    consistent match set makes the two metrics comparable per layer)."""
    pairs = _match_by_string_then_time(predicted_layers, ground_truth_layers)
    if not pairs:
        return 1.0  # maximal error when nothing could be matched at all
    total_dist = sum(_levenshtein(p["string"], g["string"]) for p, g in pairs)
    total_len = sum(max(1, len(g["string"])) for _p, g in pairs)
    return total_dist / total_len


def beat_lock_offset_error(predicted_offset_frames: int, ground_truth_offset_frames: int) -> int:
    return abs(predicted_offset_frames - ground_truth_offset_frames)


def motion_primitive_accuracy(predicted: list[str], ground_truth: list[str]) -> float:
    """Accuracy over shots where ground truth SPECIFIES a primitive -
    entries where ground_truth is None (not annotated) are excluded from
    both numerator and denominator, not counted as wrong."""
    pairs = [(p, g) for p, g in zip(predicted, ground_truth) if g is not None]
    if not pairs:
        return 0.0
    correct = sum(1 for p, g in pairs if p == g)
    return correct / len(pairs)
