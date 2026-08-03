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

from pathlib import Path

from scenedetect import SceneManager, open_video
from scenedetect.detectors import AdaptiveDetector, ContentDetector

from schemas.models import Transition

CONTENT_DETECTOR_THRESHOLD = 27.0
ADAPTIVE_DETECTOR_THRESHOLD = 3.0


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

    IMPLEMENTED IN UNIT 1.5 (needs signals.motion.estimate_affine_motion for
    the zoom branch, per INSTRUCTIONS.md's 1.4 -> 1.6 -> 1.5 build order) -
    detect_boundaries() above is the Unit 1.4 half, already complete.
    """
    raise NotImplementedError
