"""
Unit 2.7 done criteria: the same Unit-2.4/2.5-style Template + BindingSet
renders via RemotionEngine to a playable MP4 where cuts happen at the
right times and at least punch_in + one text animation primitive are
visibly correct. This unit's bar (per INSTRUCTIONS.md) is "the Node
bridge works end-to-end for a non-trivial template," not the Phase 2
blind-viewer quality bar (that's Unit 2.9, which needs human viewers and
is separately flagged as blocked).

Genuinely slow (Remotion bundles + launches headless Chrome) - marked
`slow` like the other real-pipeline integration tests in this repo.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from render.engines.remotion_engine import RemotionEngine
from render.interface import RenderOptions
from schemas.models import (
    AssetBinding,
    AudioRef,
    BindingSet,
    DurationFlex,
    Easing,
    MotionCurve,
    MotionPrimitive,
    Slot,
    SlotApplied,
    SlotRequirements,
    TextAnimation,
    TextBox,
    TextLayer,
    TextLayerAnimation,
    TextRole,
    TextStyle,
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


def _slot(slot_id: str, order: int, duration_s: float, primitive=MotionPrimitive.static, effects=None) -> Slot:
    return Slot(
        slot_id=slot_id,
        order=order,
        duration_s=duration_s,
        duration_flex=DurationFlex(min_s=duration_s * 0.75, max_s=duration_s * 1.25, snap="none"),
        requirements=SlotRequirements(),
        applied=SlotApplied(
            motion=MotionCurve(primitive=primitive, from_scale=1.0, to_scale=1.15, residual=0.01, easing=Easing.ease_out),
            grade_ref="grade_ref_placeholder",
            out_transition="cut",
            effects=effects or [],
        ),
        human_instruction=f"Drop a clip here (~{duration_s:.1f}s).",
    )


@pytest.mark.slow
def test_remotion_render_produces_correct_duration_mp4(tmp_path) -> None:
    clip_a = tmp_path / "clip_a.mp4"
    clip_b = tmp_path / "clip_b.mp4"
    _make_asset_clip(clip_a, "red", 1.5)
    _make_asset_clip(clip_b, "0x14C83A", 1.0)

    template = Template(
        source_trace_hash="deadbeef",
        source_fps=30,
        slots=[
            _slot("slot_01", 1, 1.5, primitive=MotionPrimitive.punch_in),
            _slot("slot_02", 2, 1.0, primitive=MotionPrimitive.static),
        ],
        audio_ref=AudioRef(),
        text_layers=[
            TextLayer(
                id="t1",
                t_in=0.1,
                t_out=1.3,
                string="HOOK TEXT",
                role=TextRole.hook_title,
                box=TextBox(x=0.5, y=0.3, w=0.8),
                style=TextStyle(size_rel=0.06, fill="#FFFFFF"),
                animation=TextLayerAnimation(**{"in": TextAnimation.pop, "out": TextAnimation.fade, "in_duration_f": 8}),
            )
        ],
    )

    bindings = BindingSet(
        binding_id="b1",
        bindings=[
            AssetBinding(
                slot_id="slot_01", asset_id=str(clip_a), in_point_s=0.0, duration_s=1.5, confidence=0.9, rationale="test"
            ),
            AssetBinding(
                slot_id="slot_02", asset_id=str(clip_b), in_point_s=0.0, duration_s=1.0, confidence=0.9, rationale="test"
            ),
        ],
        unresolved_slots=[],
    )

    engine = RemotionEngine()
    opts = RenderOptions(resolution=(320, 568), output_path=tmp_path / "out.mp4")
    report = engine.render(template, bindings, opts)

    assert report.output_path.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(report.output_path)],
        check=True, capture_output=True, text=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert duration == pytest.approx(2.5, abs=0.15)
