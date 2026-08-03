"""
L1 - shot boundary detection and transition classification.
See RECUT_SPEC.md sec 3.1.

Hard requirements carried over from the spec (do not regress these when
optimizing):
- Run PySceneDetect AdaptiveDetector + ContentDetector in parallel and
  reconcile (union then de-duplicate near-adjacent boundaries), don't pick
  one detector.
- `min_scene_len` MUST be 2-3 frames (common.config.Settings.
  scene_detect_min_scene_len_frames), never the library default. Short-form
  cuts every 6-10 frames and the default merges them - this is the single
  highest-value tuning knob in this module, verify it on the golden set
  before touching anything else.
- Every classified boundary must carry the TransitionEvidence that licenses
  the classification (see schemas/models.py) - this is what L2's evidence
  gate checks against.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from scenedetect import SceneManager, open_video
from scenedetect.detectors import AdaptiveDetector, ContentDetector

from schemas.models import Transition, TransitionEvidence, TransitionType
from signals.motion import estimate_affine_motion

CONTENT_DETECTOR_THRESHOLD = 27.0
ADAPTIVE_DETECTOR_THRESHOLD = 3.0

# Unit 1.5 tunables - see module docstring / INSTRUCTIONS.md Unit 1.5.
FLASH_SIGMA_THRESHOLD = 2.0
WHIP_FLOW_MAGNITUDE_PX = 15.0
ZOOM_SCALE_JUMP_THRESHOLD = 0.05
DISSOLVE_MIN_WINDOW_F = 3
DISSOLVE_MAX_WINDOW_F = 15
DISSOLVE_ELEVATED_HIST_DISTANCE = 0.15
CUT_HIST_DISTANCE_THRESHOLD = 0.3  # Bhattacharyya distance - retune against Unit 1.19's golden set
_CLASSIFY_WINDOW_FRAMES = 16  # frames examined on each side of a boundary
_MIN_BASELINE_LUM_STD = 3.0  # floor on the flash-sigma denominator, see _classify_boundary docstring


def reconcile_detectors(adaptive_boundaries: list[float], content_boundaries: list[float], *, fps: int) -> list[float]:
    """Union two detector outputs, merging boundaries within ~1 frame of
    each other. Kept as a standalone function so eval/ can unit test the
    reconciliation logic against synthetic boundary lists without running
    real CV (see eval/fixtures.py).
    """
    merged = sorted(set(adaptive_boundaries) | set(content_boundaries))
    if not merged:
        return []
    tolerance_s = 1.0 / fps
    result = [merged[0]]
    for t in merged[1:]:
        # Compare against the last KEPT boundary (not the previous raw
        # value) so a run of near-duplicates collapses to one, keeping the
        # earliest timestamp in the run.
        if t - result[-1] <= tolerance_s:
            continue
        result.append(t)
    return result


def _run_detector(video_path: Path, detector, *, fps_hint: int | None = None) -> list[float]:
    """Runs a single PySceneDetect detector end to end, returns boundary
    timestamps in seconds (scene START times, excluding t=0 - a boundary is
    a CUT POINT, not the first shot's own start)."""
    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(detector)
    scene_manager.detect_scenes(video=video)
    scene_list = scene_manager.get_scene_list()
    return [scene[0].seconds for scene in scene_list[1:]]


def detect_boundaries(normalized_video_path: Path, *, min_scene_len_frames: int) -> list[float]:
    """Unit 1.4: boundary TIMES only, no transition-type classification
    (that's detect_cuts(), Unit 1.5, built on top of this). Runs
    ContentDetector and AdaptiveDetector in parallel against the
    normalized, watermark-masked video and reconciles them - never run
    only one detector, and min_scene_len_frames MUST come from
    common.config.Settings.scene_detect_min_scene_len_frames (default 3),
    never the library default of 15 (spec sec 3.1's central warning: default
    settings merge the 6-10 frame shots short-form editors use routinely).
    """
    content_boundaries = _run_detector(
        normalized_video_path,
        ContentDetector(threshold=CONTENT_DETECTOR_THRESHOLD, min_scene_len=min_scene_len_frames),
    )
    adaptive_boundaries = _run_detector(
        normalized_video_path,
        AdaptiveDetector(adaptive_threshold=ADAPTIVE_DETECTOR_THRESHOLD, min_scene_len=min_scene_len_frames),
    )
    # fps for the merge-tolerance calculation: re-derive from the video
    # itself rather than trusting a caller-supplied value that could be stale.
    probe_video = open_video(str(normalized_video_path))
    fps = round(probe_video.frame_rate)
    return reconcile_detectors(adaptive_boundaries, content_boundaries, fps=fps)


def _read_frame_range(video_path: Path, start_frame: int, end_frame: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    start_frame = max(0, start_frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frames = []
    for _ in range(max(0, end_frame - start_frame)):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def _hsv_hist(frame: np.ndarray):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def _hist_distance(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    return float(cv2.compareHist(_hsv_hist(frame_a), _hsv_hist(frame_b), cv2.HISTCMP_BHATTACHARYYA))


def _avg_flow_vector(frames: list[np.ndarray]) -> tuple[tuple[float, float], float] | None:
    if len(frames) < 2:
        return None
    vectors = []
    for a, b in zip(frames[:-1], frames[1:]):
        gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        flow = cv2.calcOpticalFlowFarneback(
            gray_a, gray_b, None, pyr_scale=0.5, levels=3, winsize=15, iterations=3,
            poly_n=5, poly_sigma=1.2, flags=0,
        )
        vectors.append((float(np.mean(flow[..., 0])), float(np.mean(flow[..., 1]))))
    mean_vx = float(np.mean([v[0] for v in vectors]))
    mean_vy = float(np.mean([v[1] for v in vectors]))
    return (mean_vx, mean_vy), math.hypot(mean_vx, mean_vy)


def _check_whip_pan(
    before_frames: list[np.ndarray], after_frames: list[np.ndarray]
) -> tuple[str, float] | None:
    """Both sides must clear the flow-magnitude threshold AND agree in
    direction (dot product > 0) - a one-sided spike must fall through to
    `cut`, per spec sec 8.3's explicit "don't over-call whip" mitigation."""
    before = _avg_flow_vector(before_frames)
    after = _avg_flow_vector(after_frames)
    if before is None or after is None:
        return None
    (bvx, bvy), b_mag = before
    (avx, avy), a_mag = after
    if b_mag < WHIP_FLOW_MAGNITUDE_PX or a_mag < WHIP_FLOW_MAGNITUDE_PX:
        return None
    if (bvx * avx + bvy * avy) <= 0:
        return None
    vx, vy = (bvx + avx) / 2, (bvy + avy) / 2
    direction = ("right" if vx > 0 else "left") if abs(vx) >= abs(vy) else ("down" if vy > 0 else "up")
    return direction, (b_mag + a_mag) / 2


def _avg_scale(frames: list[np.ndarray]) -> float | None:
    if len(frames) < 2:
        return None
    scales = []
    for a, b in zip(frames[:-1], frames[1:]):
        M, _inliers = estimate_affine_motion(a, b)
        if M is None:
            continue
        scales.append(math.sqrt(M[0, 0] ** 2 + M[1, 0] ** 2))
    return float(np.mean(scales)) if scales else None


def _check_zoom_discontinuity(before_frames: list[np.ndarray], after_frames: list[np.ndarray]) -> float | None:
    before_scale = _avg_scale(before_frames)
    after_scale = _avg_scale(after_frames)
    if before_scale is None or after_scale is None:
        return None
    return after_scale - before_scale


def _check_dissolve(window_frames: list[np.ndarray]) -> bool:
    """Sustained elevated hist distance over a contiguous 3-15 frame run -
    NOT a single-frame spike (that's a cut) and not the whole window (that
    would just be two very different shots, not a blend)."""
    if len(window_frames) < DISSOLVE_MIN_WINDOW_F + 1:
        return False
    distances = [_hist_distance(a, b) for a, b in zip(window_frames[:-1], window_frames[1:])]
    max_run = 0
    current = 0
    for d in distances:
        if d > DISSOLVE_ELEVATED_HIST_DISTANCE:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return DISSOLVE_MIN_WINDOW_F <= max_run <= DISSOLVE_MAX_WINDOW_F


def _classify_boundary(video_path: Path, t: float, prev_t: float, next_t: float, fps: float) -> Transition:
    boundary_frame = int(round(t * fps))
    prev_frame = int(round(prev_t * fps))
    next_bound_frame = int(round(next_t * fps))

    baseline_start = max(prev_frame, boundary_frame - _CLASSIFY_WINDOW_FRAMES)
    baseline_frames = _read_frame_range(video_path, baseline_start, boundary_frame)
    after_bound = min(boundary_frame + _CLASSIFY_WINDOW_FRAMES, next_bound_frame)
    boundary_and_after = _read_frame_range(video_path, boundary_frame, after_bound)

    if not baseline_frames or not boundary_and_after:
        # Not enough surrounding frames to classify (e.g. boundary at the
        # very start/end of the video) - default to cut, low confidence.
        return Transition(
            type=TransitionType.cut,
            confidence=0.5,
            evidence=TransitionEvidence(
                detector="insufficient_frames", metric_name="n/a", metric_value=0.0, threshold_used=0.0
            ),
        )

    # 1. FLASH: boundary-frame luminance vs the shot's OWN baseline (its
    # recent frames, not the whole video), per spec sec 3.1.
    #
    # _MIN_BASELINE_LUM_STD floors the denominator: a near-flat shot (solid
    # color card, black intro) has near-zero natural luminance variance, so
    # ANY content change at the next cut - not just a real flash - produces
    # an arbitrarily large sigma and gets misclassified as flash. Real
    # footage always carries some baseline noise/texture; this floor is
    # that assumed noise level, not a threshold on the flash effect itself.
    baseline_lum = [float(np.mean(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))) for f in baseline_frames]
    baseline_mean = float(np.mean(baseline_lum))
    baseline_std = max(float(np.std(baseline_lum)), _MIN_BASELINE_LUM_STD)
    boundary_lum = float(np.mean(cv2.cvtColor(boundary_and_after[0], cv2.COLOR_BGR2GRAY)))
    flash_sigma = (boundary_lum - baseline_mean) / baseline_std
    if flash_sigma > FLASH_SIGMA_THRESHOLD:
        return Transition(
            type=TransitionType.flash,
            confidence=min(1.0, flash_sigma / 4),
            evidence=TransitionEvidence(
                detector="luminance_sigma", metric_name="flash_sigma",
                metric_value=flash_sigma, threshold_used=FLASH_SIGMA_THRESHOLD,
            ),
        )

    before_window = baseline_frames[-4:]
    after_window = boundary_and_after[:4]

    # 2. WHIP_PAN: flow-magnitude spike on BOTH sides, direction-consistent.
    whip = _check_whip_pan(before_window, after_window)
    if whip is not None:
        direction, magnitude = whip
        return Transition(
            type=TransitionType.whip_pan,
            direction=direction,
            confidence=min(1.0, magnitude / 30),
            evidence=TransitionEvidence(
                detector="flow_spike_both_sides", metric_name="flow_magnitude_px",
                metric_value=magnitude, threshold_used=WHIP_FLOW_MAGNITUDE_PX,
            ),
        )

    # 3. ZOOM: affine-scale discontinuity across the boundary.
    zoom_jump = _check_zoom_discontinuity(before_window, after_window)
    if zoom_jump is not None and abs(zoom_jump) > ZOOM_SCALE_JUMP_THRESHOLD:
        return Transition(
            type=TransitionType.zoom,
            confidence=min(1.0, abs(zoom_jump) / 0.2),
            evidence=TransitionEvidence(
                detector="affine_scale_discontinuity", metric_name="scale_jump",
                metric_value=zoom_jump, threshold_used=ZOOM_SCALE_JUMP_THRESHOLD,
            ),
        )

    # 4. DISSOLVE: sustained elevated hist distance over a 3-15 frame window.
    dissolve_window = baseline_frames[-8:] + boundary_and_after[:8]
    if _check_dissolve(dissolve_window):
        return Transition(
            type=TransitionType.dissolve,
            duration_f=len(dissolve_window),
            evidence=TransitionEvidence(
                detector="hist_distance_sustained", metric_name="sustained_run_frames",
                metric_value=float(len(dissolve_window)), threshold_used=float(DISSOLVE_MIN_WINDOW_F),
            ),
        )

    # 5. CUT: default/fallback - single-frame HSV histogram distance spike.
    hist_distance = _hist_distance(baseline_frames[-1], boundary_and_after[0])
    return Transition(
        type=TransitionType.cut,
        confidence=1.0,
        evidence=TransitionEvidence(
            detector="hsv_hist_spike", metric_name="hsv_hist_distance",
            metric_value=hist_distance, threshold_used=CUT_HIST_DISTANCE_THRESHOLD,
        ),
    )


def detect_cuts(normalized_video_path: Path, *, min_scene_len_frames: int) -> list[Transition]:
    """Returns transitions in timeline order, each already classified into
    one of: cut, dissolve, whip_pan, flash, zoom (see TransitionType).

    Classification order matters - check in this priority, first match wins,
    because e.g. a whip pan can also show a momentary luminance spike:
        1. flash        (luminance mean spike > 2 sigma)
        2. whip_pan     (optical-flow magnitude spike on BOTH sides, blur-matched)
        3. zoom         (scale discontinuity in the affine model)
        4. dissolve     (sustained elevated hist distance over 3-15 frames, monotonic)
        5. cut          (single-frame HSV histogram distance spike) - default/fallback

    A boundary that doesn't clear the whip_pan flow-spike-on-both-sides test
    must default to `cut`, per spec sec 8.3 ("whip read as a cut" mitigation)
    - do not guess whip_pan on a one-sided flow spike.
    """
    boundaries = detect_boundaries(normalized_video_path, min_scene_len_frames=min_scene_len_frames)
    if not boundaries:
        return []

    cap = cv2.VideoCapture(str(normalized_video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    shot_starts = [0.0] + boundaries
    transitions = []
    for i, t in enumerate(boundaries):
        prev_t = shot_starts[i]
        next_t = boundaries[i + 1] if i + 1 < len(boundaries) else total_frames / fps
        transitions.append(_classify_boundary(normalized_video_path, t, prev_t, next_t, fps))
    return transitions
