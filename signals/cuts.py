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

from schemas.models import Transition


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
    raise NotImplementedError


def reconcile_detectors(adaptive_boundaries: list[float], content_boundaries: list[float], *, fps: int) -> list[float]:
    """Union two detector outputs, merging boundaries within ~1 frame of
    each other. Kept as a standalone function so eval/ can unit test the
    reconciliation logic against synthetic boundary lists without running
    real CV (see eval/fixtures.py).
    """
    raise NotImplementedError
