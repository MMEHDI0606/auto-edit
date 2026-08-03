"""
Process-wide configuration, loaded once from environment / .env.

Responsibilities:
- Central place for tunables called out repeatedly in RECUT_SPEC.md so they
  are not hand-copied into each module (min_scene_len, OCR sample fps, etc).
- Nothing in signals/, semantics/, compiler/ should read os.environ directly -
  import Settings from here instead, so eval/run.py can override tunables
  per experiment without env-var juggling.

Fill in with pydantic-settings BaseSettings once dependencies are pinned
(see BUILD_ORDER.md Phase 0).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # --- L0 ingest ---
    normalize_fps: int = 30
    normalize_width: int = 1080
    normalize_height: int = 1920
    normalize_crf: int = 18
    cache_root: str = "./data/cache"

    # --- L1 signal ---
    scene_detect_min_scene_len_frames: int = 3  # spec sec 3.1: NOT the pyscenedetect default
    ocr_sample_fps: int = 8  # spec sec 3.3: not 1fps, text can flash <500ms
    flow_method_primary: str = "orb_affine"
    flow_method_fallback: str = "farneback"
    flow_inlier_fallback_threshold: int = 20  # below this inlier count, fall back to dense flow

    # --- L2 semantics ---
    triage_model_id: str = "unset-pin-before-phase-3"
    deep_pass_model_id: str = "unset-pin-before-phase-3"

    # --- L4 matcher ---
    max_asset_reuse_count: int = 2

    # --- L5 render ---
    render_width: int = 1080
    render_height: int = 1920
    render_crf: int = 20
    primary_render_engine: str = "remotion"  # see DESIGN_NOTES.md "Renderer choice"


def load_settings() -> Settings:
    """Load from env / .env, falling back to the defaults above.

    TODO(Phase 0): wire to pydantic-settings so CI and local dev can override
    via .env without touching this file.
    """
    return Settings()
