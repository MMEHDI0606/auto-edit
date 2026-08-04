"""
Unit 3.2 done criteria: running build_evidence_pack against a real trace +
normalized video produces one contact-sheet PNG per shot plus one
whole-video sheet, readable by opening them manually, with burned-in
timestamps matching the trace's t_in/t_out. Uses tests/fixtures/
synthetic_clip.mp4 - a real, decodable, license-free video with exactly-known
ground truth (3 shots, cuts at 1.2s/2.0s, 3.5s total - see
tests/fixtures/make_synthetic_clip.py) rather than a hand-rolled fake, so
this exercises the real cv2 frame-seek/decode path.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from schemas.models import (
    AudioTrace,
    EditTrace,
    EvidenceMeta,
    MotionCurve,
    MotionPrimitive,
    Shot,
    SourceInfo,
    Transition,
    TransitionType,
)
from semantics.evidence_pack import build_evidence_pack

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


def _shot(shot_id: str, t_in: float, t_out: float) -> Shot:
    return Shot(
        id=shot_id,
        t_in=t_in,
        t_out=t_out,
        in_transition=Transition(type=TransitionType.cut),
        out_transition=Transition(type=TransitionType.cut),
        motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01),
    )


def _make_trace(content_hash: str) -> EditTrace:
    return EditTrace(
        source=SourceInfo(hash=content_hash, duration_s=3.5, fps=30, w=1080, h=1920),
        audio=AudioTrace(tempo_bpm=120.0, beat_grid_s=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]),
        shots=[
            _shot("shot1", 0.0, 1.2),
            _shot("shot2", 1.2, 2.0),
            _shot("shot3", 2.0, 3.5),
        ],
        evidence=EvidenceMeta(cut_detector="adaptive+content", ocr_fps=2, flow_method="farneback"),
    )


def test_build_evidence_pack_produces_one_contact_sheet_per_shot_and_a_whole_video_sheet(tmp_path) -> None:
    trace = _make_trace("evidencepack_test_hash")
    pack = build_evidence_pack(trace, FIXTURE_PATH, cache_dir=tmp_path)

    assert [cs.shot_id for cs in pack.contact_sheets] == ["shot1", "shot2", "shot3"]
    for contact_sheet in pack.contact_sheets:
        assert contact_sheet.image_path.exists()
        img = Image.open(contact_sheet.image_path)
        # 3 tiles (first/mid/last) side by side -> width is a multiple of a
        # single 1080-wide frame (allowing for aspect-preserving resize).
        assert img.width > img.height  # 3x1080 wide x 1920 tall, landscape overall despite portrait source

    assert pack.whole_video_low_res_sheet.exists()
    whole_sheet = Image.open(pack.whole_video_low_res_sheet)
    assert whole_sheet.width > 0 and whole_sheet.height > 0


def test_build_evidence_pack_caches_and_does_not_regenerate_on_second_call(tmp_path) -> None:
    trace = _make_trace("evidencepack_cache_test_hash")
    pack1 = build_evidence_pack(trace, FIXTURE_PATH, cache_dir=tmp_path)
    first_mtime = pack1.contact_sheets[0].image_path.stat().st_mtime_ns
    first_whole_mtime = pack1.whole_video_low_res_sheet.stat().st_mtime_ns

    pack2 = build_evidence_pack(trace, FIXTURE_PATH, cache_dir=tmp_path)
    second_mtime = pack2.contact_sheets[0].image_path.stat().st_mtime_ns
    second_whole_mtime = pack2.whole_video_low_res_sheet.stat().st_mtime_ns

    assert first_mtime == second_mtime
    assert first_whole_mtime == second_whole_mtime


def test_build_evidence_pack_places_files_under_content_hash_directory(tmp_path) -> None:
    trace = _make_trace("some_specific_hash_value")
    pack = build_evidence_pack(trace, FIXTURE_PATH, cache_dir=tmp_path)

    for contact_sheet in pack.contact_sheets:
        assert "some_specific_hash_value" in str(contact_sheet.image_path)
    assert "some_specific_hash_value" in str(pack.whole_video_low_res_sheet)
