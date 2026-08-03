"""
L4 - per-asset feature extraction: duration/orientation/fps (delegates to
ingest/probe.py), face detection, shot-type classification, motion score,
CLIP embedding, optional Whisper if speech is present. See RECUT_SPEC.md
sec 6, step 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AssetFeatures:
    asset_id: str
    duration_s: float
    orientation: str
    has_face: bool
    shot_type_guess: str | None
    motion_score: float
    clip_embedding: list[float]
    has_speech: bool


def extract_asset_features(asset_path: Path, asset_id: str) -> AssetFeatures:
    raise NotImplementedError
