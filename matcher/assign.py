"""
L4 orchestrator - solves the (asset, slot) assignment via the Hungarian
algorithm under the constraint that each asset is used at most
Settings.max_asset_reuse_count times, then picks the in-point within each
asset and snaps to the beat grid using compiler.beat_snap (shared
definition - do not re-derive snapping logic here).

See RECUT_SPEC.md sec 6, steps 3-5. Rule that must not be relaxed: "never
silently misplace a clip - surface it with confidence + rationale" (spec's
own words). Every AssetBinding must carry a human-readable rationale
string; a binding below a to-be-tuned confidence floor goes into
BindingSet.unresolved_slots instead of being force-assigned.
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from compiler.beat_snap import snap_duration_to_beat
from matcher.probe import AssetFeatures, frame_diff_motion_score
from matcher.score import cost_matrix
from schemas.models import AssetBinding, BindingSet, Slot, SlotRequirements, Template

CONFIDENCE_FLOOR = 0.4  # starting point, per Unit 3.8 - tune against Unit 3.9's blind-viewer numbers

_IN_POINT_STEP_S = 0.1  # window slide step, per Unit 3.8's own suggested granularity
_WINDOW_SAMPLE_COUNT = 4  # frames sampled within one candidate window to score it


def _window_frames(cap: cv2.VideoCapture, start_s: float, duration_s: float, fps: float) -> list[np.ndarray]:
    frames = []
    for i in range(_WINDOW_SAMPLE_COUNT):
        t = start_s + duration_s * i / max(1, _WINDOW_SAMPLE_COUNT - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(t * fps))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    return frames


def _candidate_starts(latest_start_s: float, step_s: float) -> list[float]:
    if latest_start_s <= 0:
        return [0.0]
    count = int(latest_start_s / step_s) + 1
    return [i * step_s for i in range(count)]


def pick_in_point(asset: AssetFeatures, *, required_duration_s: float) -> float:
    """Sub-window of `required_duration_s` with the highest motion/quality
    score within the asset; returns the in-point in seconds."""
    latest_start_s = max(0.0, asset.duration_s - required_duration_s)

    cap = cv2.VideoCapture(asset.asset_path)
    if not cap.isOpened():
        raise ValueError(f"could not open {asset.asset_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        best_start, best_score = 0.0, -1.0
        for start in _candidate_starts(latest_start_s, _IN_POINT_STEP_S):
            frames = _window_frames(cap, start, required_duration_s, fps)
            score = frame_diff_motion_score(frames) if len(frames) >= 2 else 0.0
            if score > best_score:
                best_start, best_score = start, score
        return best_start
    finally:
        cap.release()


def _build_rationale(asset: AssetFeatures, requirements: SlotRequirements, score: float) -> str:
    reasons: list[str] = []
    if requirements.role:
        reasons.append(f"closest CLIP match for role={requirements.role}")
    if requirements.needs_face:
        reasons.append("face present as required" if asset.has_face else "no face found despite requirement")
    if requirements.shot_type_pref:
        reasons.append(f"shot_type_guess={asset.shot_type_guess!r} vs preferred {requirements.shot_type_pref}")
    if requirements.motion_pref:
        reasons.append(f"motion_pref target={requirements.motion_pref}")
    if not reasons:
        reasons.append("best available match, no strong slot constraints")
    return f"{'; '.join(reasons)} (score={score:.2f})"


def build_binding(
    slot: Slot,
    asset: AssetFeatures,
    *,
    slot_start_s: float,
    beat_grid_s: list[float],
    median_cut_offset_frames: int,
    fps: int,
    confidence: float,
    rationale: str,
) -> tuple[AssetBinding, float]:
    """Builds one AssetBinding: picks the best in-point within `asset`,
    beat-snaps the slot's duration against `slot_start_s` (the slot's
    position on the TEMPLATE's own timeline, NOT a position within the
    asset - see match_assets' own note on this). Returns (binding,
    snapped_duration_s) - the caller advances its own timeline cursor by
    the returned duration, since only the caller knows whether it's
    iterating every slot in order (match_assets()) or a caller-supplied
    subset (recut_mcp.tools.bind(), Unit 4.3).

    Shared by match_assets() (automatic proposals) and recut_mcp.tools.bind()
    (user-confirmed/overridden picks) so the actual in-point/beat-snap
    math exists in exactly one place.
    """
    in_point_s = pick_in_point(asset, required_duration_s=slot.duration_s)

    snapped_duration_s, _was_snapped = snap_duration_to_beat(
        min_s=slot.duration_flex.min_s,
        max_s=slot.duration_flex.max_s,
        nominal_s=slot.duration_s,
        t_start_s=slot_start_s,
        beat_grid_s=beat_grid_s,
        median_cut_offset_frames=median_cut_offset_frames,
        fps=fps,
    )

    binding = AssetBinding(
        slot_id=slot.slot_id,
        asset_id=asset.asset_id,
        in_point_s=in_point_s,
        duration_s=snapped_duration_s,
        confidence=confidence,
        rationale=rationale,
    )
    return binding, snapped_duration_s


def match_assets(template: Template, assets: list[AssetFeatures], *, max_reuse: int) -> BindingSet:
    """Full L4 pipeline: cost matrix -> constrained Hungarian assignment ->
    per-slot in-point selection + beat snap -> BindingSet with confidences
    and rationales. Slots the solver can't confidently fill go into
    BindingSet.unresolved_slots, never a forced low-confidence guess.
    """
    if not assets or not template.slots:
        return BindingSet(binding_id=str(uuid.uuid4()), bindings=[], unresolved_slots=[s.slot_id for s in template.slots])

    all_requirements = [slot.requirements for slot in template.slots]
    base_costs = cost_matrix(assets, all_requirements)

    # scipy's linear_sum_assignment assumes each row (asset) used at most
    # once - replicate each asset's row up to max_reuse times so it can be
    # picked for up to max_reuse slots, then map assignments back to the
    # real asset id afterward (Unit 3.8's own stated approach).
    expanded_costs: list[list[float]] = []
    expanded_asset_indices: list[int] = []
    for asset_index, row in enumerate(base_costs):
        for _ in range(max_reuse):
            expanded_costs.append(row)
            expanded_asset_indices.append(asset_index)

    row_ind, col_ind = linear_sum_assignment(np.array(expanded_costs))

    # A virtual-copy row could theoretically be assigned to more than one
    # slot only if scipy's solver produced duplicate rows in its solution,
    # which it doesn't (each row index appears at most once in row_ind) -
    # but two DIFFERENT virtual copies of the SAME asset could each win a
    # different slot; keep only the best-scoring slot per (slot) here and
    # let every slot see its true best candidate.
    best_per_slot: dict[int, tuple[int, float]] = {}
    for row, col in zip(row_ind, col_ind):
        score = 1.0 - expanded_costs[row][col]
        asset_index = expanded_asset_indices[row]
        if col not in best_per_slot or score > best_per_slot[col][1]:
            best_per_slot[col] = (asset_index, score)

    bindings: list[AssetBinding] = []
    unresolved_slots: list[str] = []
    # Each slot's position on the FINAL TIMELINE (what beat_grid_s is
    # measured against) - NOT the same axis as in_point_s, which is a
    # position within the bound ASSET's own footage. Advances by each
    # slot's actual (possibly beat-snapped) duration regardless of whether
    # that slot ends up resolved, since later slots still play at their
    # sequential position either way.
    timeline_cursor_s = 0.0

    for slot_index, slot in enumerate(template.slots):
        slot_start_s = timeline_cursor_s

        if slot_index not in best_per_slot:
            unresolved_slots.append(slot.slot_id)
            timeline_cursor_s += slot.duration_s
            continue

        asset_index, score = best_per_slot[slot_index]
        if score < CONFIDENCE_FLOOR:
            unresolved_slots.append(slot.slot_id)
            timeline_cursor_s += slot.duration_s
            continue

        asset = assets[asset_index]
        binding, snapped_duration_s = build_binding(
            slot,
            asset,
            slot_start_s=slot_start_s,
            beat_grid_s=template.audio_ref.beat_grid_s,
            median_cut_offset_frames=template.audio_ref.median_cut_offset_frames,
            fps=template.source_fps,
            confidence=score,
            rationale=_build_rationale(asset, slot.requirements, score),
        )
        timeline_cursor_s += snapped_duration_s
        bindings.append(binding)

    return BindingSet(binding_id=str(uuid.uuid4()), bindings=bindings, unresolved_slots=unresolved_slots)
