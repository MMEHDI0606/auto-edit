"""
Unit 4.3 done criteria: register 3-5 local test assets, call match_assets
against a real template, confirm proposed bindings + confidences come
back, call bind with the user accepting (or overriding) them, confirm a
binding_id is returned and retrievable.

Marked slow where real feature extraction (CLIP/whisper) or real cv2
in-point scanning is involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.store import BindingStore, TemplateStore
from recut_mcp.tools import analyze_video, bind, describe_template, get_template, list_slots, match_assets, register_assets
from schemas.models import AudioRef, DurationFlex, MotionCurve, MotionPrimitive, Slot, SlotApplied, SlotRequirements, Template

FACE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_face_clip.mp4"
NO_FACE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_clip.mp4"


def _hand_built_template() -> Template:
    return Template(
        source_trace_hash="deadbeef",
        source_fps=30,
        slots=[
            Slot(
                slot_id="slot_01",
                order=1,
                duration_s=1.0,
                duration_flex=DurationFlex(min_s=0.75, max_s=1.25, snap="none"),
                requirements=SlotRequirements(),
                applied=SlotApplied(motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01)),
                human_instruction="This is your hook shot (~1.0s).",
            ),
            Slot(
                slot_id="slot_02",
                order=2,
                duration_s=0.8,
                duration_flex=DurationFlex(min_s=0.6, max_s=1.0, snap="none"),
                requirements=SlotRequirements(),
                applied=SlotApplied(motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01)),
                human_instruction="Drop a clip here (~0.8s).",
            ),
        ],
        audio_ref=AudioRef(),
    )


def test_get_template_requires_recut_format(fake_redis_server) -> None:
    from api.store import JobStore

    job_store = JobStore()
    job_id = job_store.create()
    template_id = TemplateStore().create(_hand_built_template())
    job_store.mark_done(job_id, result_refs={"trace_path": "/x", "template_id": template_id})

    with pytest.raises(NotImplementedError):
        get_template(job_id, format="otio")


def test_get_template_without_full_depth_analysis_raises(fake_redis_server) -> None:
    from api.store import JobStore

    job_store = JobStore()
    job_id = job_store.create()
    job_store.mark_done(job_id, result_refs={"trace_path": "/x"})  # no template_id - depth="fast" shape

    with pytest.raises(ValueError):
        get_template(job_id)


def test_get_template_returns_native_json(fake_redis_server) -> None:
    from api.store import JobStore

    job_store = JobStore()
    job_id = job_store.create()
    template_id = TemplateStore().create(_hand_built_template())
    job_store.mark_done(job_id, result_refs={"trace_path": "/x", "template_id": template_id})

    result = get_template(job_id)
    assert result["template_id"] == template_id
    assert len(result["template"]["slots"]) == 2


def test_describe_template_reads_the_edit(fake_redis_server) -> None:
    template_id = TemplateStore().create(_hand_built_template())
    result = describe_template(template_id)
    assert result["slot_count"] == 2
    assert "This is your hook shot" in result["description"]
    assert "Drop a clip here" in result["description"]


def test_list_slots_returns_every_slot(fake_redis_server) -> None:
    template_id = TemplateStore().create(_hand_built_template())
    slots = list_slots(template_id)
    assert [s["slot_id"] for s in slots] == ["slot_01", "slot_02"]


@pytest.mark.slow
def test_register_match_and_bind_end_to_end(fake_redis_server) -> None:
    if not (FACE_FIXTURE.exists() and NO_FACE_FIXTURE.exists()):
        pytest.skip("run tests/fixtures/make_face_clip.py and make_synthetic_clip.py first")

    template_id = TemplateStore().create(_hand_built_template())

    asset_ids = register_assets([str(FACE_FIXTURE), str(NO_FACE_FIXTURE), str(NO_FACE_FIXTURE)])
    assert len(asset_ids) == 3

    proposal = match_assets(template_id, asset_ids)
    assert "proposed_bindings" in proposal
    assert "unresolved_slots" in proposal
    for binding in proposal["proposed_bindings"]:
        assert "confidence" in binding
        assert "rationale" in binding
        assert binding["rationale"]  # never empty

    # User accepts the proposal (as-is - no overrides).
    slot_to_asset = {b["slot_id"]: b["asset_id"] for b in proposal["proposed_bindings"]}
    binding_id = bind(template_id, slot_to_asset)

    assert isinstance(binding_id, str) and binding_id

    persisted = BindingStore().get(binding_id)
    assert persisted.binding_id == binding_id
    assert len(persisted.bindings) == len(slot_to_asset)
    for binding in persisted.bindings:
        assert binding.rationale
        assert binding.confidence == 1.0  # bind() records user choices at full confidence


@pytest.mark.slow
def test_bind_with_user_override_leaves_unmapped_slots_unresolved(fake_redis_server) -> None:
    if not NO_FACE_FIXTURE.exists():
        pytest.skip("run tests/fixtures/make_synthetic_clip.py first")

    template_id = TemplateStore().create(_hand_built_template())
    asset_ids = register_assets([str(NO_FACE_FIXTURE)])

    # Only bind slot_01 - slot_02 deliberately left unmapped.
    binding_id = bind(template_id, {"slot_01": asset_ids[0]})

    persisted = BindingStore().get(binding_id)
    assert [b.slot_id for b in persisted.bindings] == ["slot_01"]
    assert persisted.unresolved_slots == ["slot_02"]
