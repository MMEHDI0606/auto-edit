"""
Process-wide configuration, loaded once from environment / .env.

Responsibilities:
- Central place for tunables called out repeatedly in RECUT_SPEC.md so they
  are not hand-copied into each module (min_scene_len, OCR sample fps, etc).
- Nothing in signals/, semantics/, compiler/ should read os.environ directly -
  import Settings from here instead, so eval/run.py can override tunables
  per experiment without env-var juggling.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECUT_", env_file=".env", frozen=True)

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

    # --- L6 MCP server / job store (Phase 4) ---
    redis_url: str = "redis://localhost:6379/0"
    # Default True: no real Celery worker process is deployed anywhere yet
    # in this environment, so tasks run in-process synchronously when
    # called via .delay()/.apply_async() - the job_id/polling contract
    # still holds (a caller still gets a job_id back immediately and polls
    # get_job), it just resolves instantly instead of asynchronously. A
    # real deployment with a separate worker process should override this
    # to False via RECUT_CELERY_TASK_ALWAYS_EAGER=false.
    celery_task_always_eager: bool = True

    # --- L6 hosted HTTP + OAuth (Unit 4.7, Phase 4b) ---
    # No default password - deliberately unset. run_http_server() refuses
    # to start (MissingAuthCredentialsError) rather than fall back to a
    # hardcoded demo credential, unlike the MCP SDK's own example
    # provider - this is real repository code, not a throwaway demo.
    mcp_auth_username: str | None = None
    mcp_auth_password: str | None = None
    mcp_oauth_scope: str = "recut"

    # --- L5 render ---
    render_width: int = 1080
    render_height: int = 1920
    render_crf: int = 20
    primary_render_engine: str = "remotion"  # see DESIGN_NOTES.md "Renderer choice"


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Process-wide singleton. Cached so every module sees the same instance;
    call `load_settings.cache_clear()` in tests that need to override env vars."""
    return Settings()
