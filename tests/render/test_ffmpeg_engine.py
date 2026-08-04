"""
Unit 2.5 done criteria: given a hand-built Template + BindingSet (the
"Unit 2.4 smoke-test binding," folded into this test rather than shipped
as a separate throwaway script - see Unit 2.4's commit), render()
produces a playable MP4 of the correct total duration with clips in the
correct order, and preview() produces a storyboard image.
"""

from __future__ import annotations

import subprocess

import pytest

from render.engines.ffmpeg_engine import FfmpegEngine
from render.interface import RenderOptions
from schemas.models import (
    AssetBinding,
    BindingSet,
    DurationFlex,
    Easing,
    MotionCurve,
    MotionPrimitive,
    Slot,
    SlotApplied,
    SlotRequirements,
    Template,
)


def _make_asset_clip(path, color: str, duration_s: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x568:d={duration_s}:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True, text=True,
    )


def _slot(slot_id: str, order: int, duration_s: float, primitive=MotionPrimitive.static, out_transition="cut") -> Slot:
    return Slot(
        slot_id=slot_id,
        order=order,
        duration_s=duration_s,
        duration_flex=DurationFlex(min_s=duration_s * 0.75, max_s=duration_s * 1.25, snap="none"),
        requirements=SlotRequirements(),
        applied=SlotApplied(
            motion=MotionCurve(primitive=primitive, residual=0.01, easing=Easing.linear),
            grade_ref="grade_ref_placeholder",
            out_transition=out_transition,
        ),
        human_instruction=f"Drop a clip here (~{duration_s:.1f}s).",
    )


@pytest.fixture()
def three_slot_template() -> Template:
    return Template(
        source_trace_hash="deadbeef",
        source_fps=30,
        slots=[
            _slot("slot_01", 1, 1.0, primitive=MotionPrimitive.punch_in, out_transition="dissolve"),
            _slot("slot_02", 2, 0.8, primitive=MotionPrimitive.static, out_transition="cut"),
            _slot("slot_03", 3, 1.2, primitive=MotionPrimitive.static, out_transition="cut"),
        ],
        audio_ref={"beat_grid_s": []},
    )


@pytest.fixture()
def bindings_with_one_unresolved(tmp_path) -> BindingSet:
    clip_a = tmp_path / "clip_a.mp4"
    clip_b = tmp_path / "clip_b.mp4"
    _make_asset_clip(clip_a, "red", 2.0)
    _make_asset_clip(clip_b, "blue", 2.0)

    return BindingSet(
        binding_id="b1",
        bindings=[
            AssetBinding(
                slot_id="slot_01", asset_id=str(clip_a), in_point_s=0.0, duration_s=1.0, confidence=0.9, rationale="test"
            ),
            AssetBinding(
                slot_id="slot_02", asset_id=str(clip_b), in_point_s=0.0, duration_s=0.8, confidence=0.9, rationale="test"
            ),
        ],
        unresolved_slots=["slot_03"],
    )


def test_render_produces_correct_total_duration_and_slot_order(three_slot_template, bindings_with_one_unresolved, tmp_path) -> None:
    engine = FfmpegEngine()
    opts = RenderOptions(resolution=(320, 568), output_path=tmp_path / "out.mp4")

    report = engine.render(three_slot_template, bindings_with_one_unresolved, opts)

    assert report.output_path.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(report.output_path)],
        check=True, capture_output=True, text=True,
    )
    import json
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert duration == pytest.approx(1.0 + 0.8 + 1.2, abs=0.15)


def test_render_flags_unresolved_slot_and_non_static_motion_and_dissolve(three_slot_template, bindings_with_one_unresolved, tmp_path) -> None:
    engine = FfmpegEngine()
    opts = RenderOptions(resolution=(320, 568), output_path=tmp_path / "out.mp4")

    report = engine.render(three_slot_template, bindings_with_one_unresolved, opts)

    assert any("slot_03" in a and "MISSING" in a for a in report.approximations)
    assert any("slot_01" in a and "punch_in" in a for a in report.approximations)
    assert any("slot_01" in a and "dissolve" in a for a in report.approximations)
    # slot_02 is static motion with a plain cut - should NOT generate a motion/dissolve flag
    assert not any(a.startswith("slot_02") for a in report.approximations)


def test_preview_produces_storyboard_image(three_slot_template, bindings_with_one_unresolved) -> None:
    engine = FfmpegEngine()
    storyboard_path = engine.preview(three_slot_template, bindings_with_one_unresolved)
    assert storyboard_path.exists()
    assert storyboard_path.suffix == ".png"
