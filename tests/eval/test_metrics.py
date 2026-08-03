"""
Unit 1.19 done criteria (metrics half - no real video needed, these are
pure functions over synthetic prediction/ground-truth pairs).
"""

from __future__ import annotations

from eval.metrics import (
    beat_lock_offset_error,
    cut_boundary_f1,
    motion_primitive_accuracy,
    text_layer_cer,
    text_layer_timing_iou,
    transition_type_accuracy,
)


def test_cut_boundary_f1_perfect_match() -> None:
    result = cut_boundary_f1([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], tolerance_frames=2, fps=30)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["tp"] == 3 and result["fp"] == 0 and result["fn"] == 0


def test_cut_boundary_f1_within_tolerance_counts_as_match() -> None:
    # 1 frame off at 30fps = 0.033s, well within +/-2 frames tolerance.
    result = cut_boundary_f1([1.033], [1.0], tolerance_frames=2, fps=30)
    assert result["tp"] == 1
    assert result["f1"] == 1.0


def test_cut_boundary_f1_outside_tolerance_is_fp_and_fn() -> None:
    result = cut_boundary_f1([1.5], [1.0], tolerance_frames=2, fps=30)
    assert result["tp"] == 0
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["f1"] == 0.0


def test_cut_boundary_f1_greedy_matching_is_globally_optimal_not_first_come() -> None:
    # Two predictions both near one ground-truth cut at 1.0 and another
    # prediction is the ONLY one near the ground-truth cut at 5.0 - a naive
    # order-dependent greedy could waste the 5.0 match on the wrong pairing.
    predicted = [1.01, 1.02, 5.0]
    ground_truth = [1.0, 5.0]
    result = cut_boundary_f1(predicted, ground_truth, tolerance_frames=2, fps=30)
    assert result["tp"] == 2  # one of {1.01,1.02} matches 1.0, and 5.0 matches 5.0
    assert result["fn"] == 0
    assert result["fp"] == 1


def test_cut_boundary_f1_empty_inputs() -> None:
    result = cut_boundary_f1([], [], tolerance_frames=2, fps=30)
    assert result == {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0}


def test_transition_type_accuracy() -> None:
    predicted = ["cut", "whip_pan", "dissolve", "cut"]
    ground_truth = ["cut", "whip_pan", "cut", "cut"]
    assert transition_type_accuracy(predicted, ground_truth) == 0.75


def test_transition_type_accuracy_empty() -> None:
    assert transition_type_accuracy([], []) == 0.0


def test_text_layer_timing_iou_matches_by_string_first() -> None:
    predicted = [
        {"string": "HOOK TEXT", "t_in": 0.2, "t_out": 1.15},
        {"string": "CTA HERE", "t_in": 3.0, "t_out": 3.5},
    ]
    ground_truth = [
        {"string": "HOOK TEXT", "t_in": 0.25, "t_out": 1.2},
        {"string": "CTA HERE", "t_in": 3.0, "t_out": 3.4},
    ]
    iou = text_layer_timing_iou(predicted, ground_truth)
    assert 0.7 < iou <= 1.0  # both layers overlap heavily but not perfectly


def test_text_layer_timing_iou_no_match_returns_zero() -> None:
    assert text_layer_timing_iou([], [{"string": "x", "t_in": 0, "t_out": 1}]) == 0.0
    assert text_layer_timing_iou([{"string": "x", "t_in": 0, "t_out": 1}], []) == 0.0


def test_text_layer_cer_exact_match_is_zero() -> None:
    predicted = [{"string": "hello world", "t_in": 0, "t_out": 1}]
    ground_truth = [{"string": "hello world", "t_in": 0, "t_out": 1}]
    assert text_layer_cer(predicted, ground_truth) == 0.0


def test_text_layer_cer_reflects_edit_distance() -> None:
    predicted = [{"string": "hallo world", "t_in": 0, "t_out": 1}]  # 1 char off
    ground_truth = [{"string": "hello world", "t_in": 0, "t_out": 1}]
    cer = text_layer_cer(predicted, ground_truth)
    assert cer == 1 / len("hello world")


def test_beat_lock_offset_error() -> None:
    assert beat_lock_offset_error(-2, -1) == 1
    assert beat_lock_offset_error(3, 3) == 0
    assert beat_lock_offset_error(-1, 2) == 3


def test_motion_primitive_accuracy_excludes_unannotated_shots() -> None:
    predicted = ["punch_in", "static", "pan"]
    ground_truth = ["punch_in", None, "whip"]  # middle shot not annotated - excluded entirely
    # only 2 annotated pairs: (punch_in,punch_in) correct, (pan,whip) wrong -> 1/2
    assert motion_primitive_accuracy(predicted, ground_truth) == 0.5


def test_motion_primitive_accuracy_all_unannotated_returns_zero() -> None:
    assert motion_primitive_accuracy(["punch_in"], [None]) == 0.0
