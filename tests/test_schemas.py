"""
Smoke tests for schemas/models.py - these should be the very first tests
that pass in this repo (before any pipeline code exists) because every
other module imports these models. Run with: pytest tests/test_schemas.py
"""

from __future__ import annotations

from schemas.models import (
    AudioRef,
    AudioTrace,
    EditTrace,
    EvidenceMeta,
    Grade,
    MotionCurve,
    Shot,
    SourceInfo,
    Template,
    Transition,
)


def test_minimal_edit_trace_round_trips() -> None:
    trace = EditTrace(
        source=SourceInfo(hash="deadbeef", duration_s=1.0, fps=30, w=1080, h=1920),
        audio=AudioTrace(),
        shots=[
            Shot(
                id="s1",
                t_in=0.0,
                t_out=1.0,
                in_transition=Transition(type="cut"),
                out_transition=Transition(type="cut"),
                motion=MotionCurve(primitive="static", residual=0.0),
                grade=Grade(),
            )
        ],
        evidence=EvidenceMeta(cut_detector="adaptive+content", ocr_fps=8, flow_method="orb_affine"),
    )
    payload = trace.model_dump_json()
    assert EditTrace.model_validate_json(payload) == trace


def test_audio_ref_cannot_permit_embedding() -> None:
    ref = AudioRef()
    assert ref.embed_permitted is False


def test_minimal_template_requires_no_embedded_audio() -> None:
    template = Template(source_trace_hash="deadbeef", source_fps=30, slots=[], audio_ref=AudioRef())
    assert template.audio_ref.embed_permitted is False
