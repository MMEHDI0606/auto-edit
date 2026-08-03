"""
L2 - builds the compact "evidence pack" handed to a VLM provider. See
RECUT_SPEC.md sec 4.1.

Never stream the whole video into a model at high FPS - build:
  - a contact sheet per shot (first/middle/last frame, tiled, burned-in
    timestamps)
  - the numeric EditTrace (already small)
  - OCR strings + transcript + beat grid

Contact sheets are cached alongside the trace (keyed by content hash + shot
id) so re-running the semantics layer (e.g. after a model upgrade) doesn't
re-render them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schemas.models import EditTrace


@dataclass
class ContactSheet:
    shot_id: str
    image_path: Path  # tiled first/middle/last frame, timestamps burned in


@dataclass
class EvidencePack:
    trace: EditTrace
    contact_sheets: list[ContactSheet]
    whole_video_low_res_sheet: Path  # for the triage pass, sec 4.2


def build_evidence_pack(trace: EditTrace, normalized_video_path: Path, *, cache_dir: Path) -> EvidencePack:
    raise NotImplementedError
