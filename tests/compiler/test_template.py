"""
Unit 2.3 done criteria: compile_template() on a synthetic EditTrace
returns a Template that validates, has one slot per shot in correct
order, and a non-empty confidence_flags list for a template with
low-confidence elements vs. an empty list for a clean cut-only template.
"""

from __future__ import annotations

from compiler.template import compile_template
from schemas.models import (
    AudioTrace,
    EditTrace,
    EffectType,
    EvidenceMeta,
    Grade,
    MotionCurve,
    MotionPrimitive,
    Shot,
    ShotContent,
    ShotEffect,
    SourceInfo,
    TextBox,
    TextLayer,
    TextLayerAnimation,
    TextStyle,
    Transition,
    TransitionType,
)


def _clean_shot(shot_id: str, t_in: float, t_out: float) -> Shot:
    return Shot(
        id=shot_id,
        t_in=t_in,
        t_out=t_out,
        in_transition=Transition(type=TransitionType.cut),
        out_transition=Transition(type=TransitionType.cut),
        motion=MotionCurve(primitive=MotionPrimitive.static, residual=0.01),
        effects=[],
        grade=Grade(),  # neutral
        content=ShotContent(),
    )


def _trace(shots: list[Shot], text_layers: list[TextLayer] | None = None) -> EditTrace:
    return EditTrace(
        source=SourceInfo(hash="deadbeef", duration_s=sum(s.t_out - s.t_in for s in shots), fps=30, w=1080, h=1920),
        audio=AudioTrace(beat_grid_s=[0.5, 1.0, 1.5]),
        shots=shots,
        text_layers=text_layers or [],
        evidence=EvidenceMeta(cut_detector="adaptive+content", ocr_fps=8, flow_method="orb_affine"),
    )


def test_compile_template_produces_one_slot_per_shot_in_order() -> None:
    trace = _trace([_clean_shot("s1", 0.0, 1.0), _clean_shot("s2", 1.0, 2.0), _clean_shot("s3", 2.0, 3.0)])
    template = compile_template(trace)
    assert len(template.slots) == 3
    assert [s.order for s in template.slots] == [1, 2, 3]
    assert [s.slot_id for s in template.slots] == ["slot_01", "slot_02", "slot_03"]


def test_clean_cut_only_template_has_no_confidence_flags() -> None:
    trace = _trace([_clean_shot("s1", 0.0, 1.0), _clean_shot("s2", 1.0, 2.0)])
    template = compile_template(trace)
    assert template.confidence_flags == []


def test_keyframed_motion_flags_confidence() -> None:
    shot = _clean_shot("s1", 0.0, 1.0)
    shot.motion = MotionCurve(primitive=MotionPrimitive.keyframed, residual=0.5, raw_keyframes=[{"t": 0}])
    template = compile_template(_trace([shot]))
    assert any("raw keyframes" in f for f in template.confidence_flags)


def test_speed_ramp_effect_flags_confidence() -> None:
    shot = _clean_shot("s1", 0.0, 1.0)
    shot.effects = [ShotEffect(type=EffectType.speed_ramp, params={"segments": []}, confidence=0.55)]
    template = compile_template(_trace([shot]))
    assert any("speed ramp" in f for f in template.confidence_flags)


def test_non_neutral_grade_flags_confidence() -> None:
    shot = _clean_shot("s1", 0.0, 1.0)
    shot.grade = Grade(contrast=1.5, saturation=1.4, temp=150.0)
    template = compile_template(_trace([shot]))
    assert any("grade" in f for f in template.confidence_flags)


def test_low_confidence_font_flags() -> None:
    layer = TextLayer(
        id="t1",
        t_in=0.2,
        t_out=1.0,
        string="HOOK",
        role="hook_title",
        box=TextBox(x=0.5, y=0.5, w=0.3),
        style=TextStyle(font_guess="Poppins", font_confidence=0.4, size_rel=0.05),
        animation=TextLayerAnimation(**{"in": "fade", "out": "fade", "in_duration_f": 6}),
    )
    template = compile_template(_trace([_clean_shot("s1", 0.0, 1.0)], text_layers=[layer]))
    assert any("Poppins" in f and "low confidence" in f for f in template.confidence_flags)


def test_audio_ref_never_permits_embedding() -> None:
    template = compile_template(_trace([_clean_shot("s1", 0.0, 1.0)]))
    assert template.audio_ref.embed_permitted is False
    assert template.audio_ref.beat_grid_s == [0.5, 1.0, 1.5]
