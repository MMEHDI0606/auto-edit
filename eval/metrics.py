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


def cut_boundary_f1(predicted_cuts_s: list[float], ground_truth_cuts_s: list[float], *, tolerance_frames: int, fps: int) -> dict:
    """Precision/recall/F1 @ +/- tolerance_frames. Target from spec sec 11
    Phase 1 gate: >=90% F1 within +/-2 frames."""
    raise NotImplementedError


def transition_type_accuracy(predicted: list[str], ground_truth: list[str]) -> float:
    raise NotImplementedError


def text_layer_timing_iou(predicted_layers: list[dict], ground_truth_layers: list[dict]) -> float:
    """Target: >=85% (spec sec 11 Phase 1 gate)."""
    raise NotImplementedError


def text_layer_cer(predicted_layers: list[dict], ground_truth_layers: list[dict]) -> float:
    """Character error rate on OCR'd strings vs ground truth."""
    raise NotImplementedError


def beat_lock_offset_error(predicted_offset_frames: int, ground_truth_offset_frames: int) -> int:
    raise NotImplementedError


def motion_primitive_accuracy(predicted: list[str], ground_truth: list[str]) -> float:
    raise NotImplementedError
