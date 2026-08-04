"""
Fallback engine for cut-only templates (no kinetic text, no complex
motion). Fastest, poorest for kinetic text - spec sec 7.1. Useful as the
Phase-1/2 smoke-test engine since it has no Node dependency at all; wire
this up FIRST if you want an end-to-end (trace -> template -> rendered
MP4) smoke test before RemotionEngine exists.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from render.interface import RenderEngine, RenderOptions, RenderReport
from render.report import add_approximation
from schemas.models import AssetBinding, BindingSet, MotionPrimitive, Slot, Template

_FONT_FILE = r"C:\Windows\Fonts\arial.ttf".replace("\\", "/").replace(":", "\\:")


class FfmpegEngine(RenderEngine):
    name = "ffmpeg"

    def render(self, template: Template, bindings: BindingSet, opts: RenderOptions) -> RenderReport:
        """Builds an ffmpeg filtergraph directly from bindings + cut points.
        No text animation, no kinetic effects - degrade every non-static
        motion primitive and every dissolve transition to a hard cut, and
        record each degradation in RenderReport.approximations. An
        unresolved slot renders as a solid placeholder frame with a burned-
        in "MISSING: {slot_id}" label - never silently skipped, so the
        output's total duration always matches the template.
        """
        approximations: list[str] = []
        binding_by_slot = {b.slot_id: b for b in bindings.bindings}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            segment_paths = []

            for slot in template.slots:
                binding = binding_by_slot.get(slot.slot_id)
                segment_path = tmp_path / f"{slot.slot_id}.mp4"

                if binding is None or slot.slot_id in bindings.unresolved_slots:
                    self._render_placeholder(segment_path, slot, opts)
                    add_approximation(approximations, slot.slot_id, "no asset bound - rendered as MISSING placeholder")
                else:
                    self._render_bound_clip(segment_path, slot, binding, opts)
                    if slot.applied.motion.primitive != MotionPrimitive.static:
                        add_approximation(
                            approximations, slot.slot_id,
                            f"{slot.applied.motion.primitive.value} motion not rendered by ffmpeg engine (cut-only)",
                        )
                    if slot.applied.out_transition.startswith("dissolve"):
                        add_approximation(
                            approximations, slot.slot_id,
                            "dissolve transition approximated as a hard cut by ffmpeg engine",
                        )

                segment_paths.append(segment_path)

            output_path = opts.output_path or Path(tempfile.mkdtemp(prefix="recut_render_")) / "render.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._concat_segments(segment_paths, output_path)

        return RenderReport(approximations=approximations, output_path=output_path)

    def preview(self, template: Template, bindings: BindingSet) -> Path:
        """Storyboard PNG - one thumbnail per slot, tiled horizontally.
        Deliberately does NOT run a full render first (single-frame
        extraction per slot only) - this is the fast iteration path spec
        sec 7.3 calls for, not a byproduct of render()."""
        binding_by_slot = {b.slot_id: b for b in bindings.bindings}
        thumb_w, thumb_h = 270, 480

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            thumb_paths = []

            for slot in template.slots:
                binding = binding_by_slot.get(slot.slot_id)
                thumb_path = tmp_path / f"{slot.slot_id}_thumb.png"
                if binding is None or slot.slot_id in bindings.unresolved_slots:
                    cmd = [
                        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={thumb_w}x{thumb_h}:d=0.1",
                        "-frames:v", "1", str(thumb_path),
                    ]
                else:
                    vf = (
                        f"scale={thumb_w}:{thumb_h}:force_original_aspect_ratio=decrease,"
                        f"pad={thumb_w}:{thumb_h}:(ow-iw)/2:(oh-ih)/2:color=black"
                    )
                    cmd = [
                        "ffmpeg", "-y", "-ss", str(binding.in_point_s), "-i", str(binding.asset_id),
                        "-vf", vf, "-frames:v", "1", str(thumb_path),
                    ]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                thumb_paths.append(thumb_path)

            output_path = Path(tempfile.mkdtemp(prefix="recut_preview_")) / "storyboard.png"
            inputs: list[str] = []
            for p in thumb_paths:
                inputs += ["-i", str(p)]
            filter_str = "".join(f"[{i}:v]" for i in range(len(thumb_paths))) + f"hstack=inputs={len(thumb_paths)}[out]"
            cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_str, "-map", "[out]", str(output_path)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

        return output_path

    def _render_bound_clip(self, out_path: Path, slot: Slot, binding: AssetBinding, opts: RenderOptions) -> None:
        w, h = opts.resolution
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(binding.in_point_s), "-i", str(binding.asset_id),
            "-t", str(slot.duration_s),
            "-vf", vf, "-r", "30",
        ]
        cmd += ["-c:a", "aac"] if opts.include_audio else ["-an"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    def _render_placeholder(self, out_path: Path, slot: Slot, opts: RenderOptions) -> None:
        w, h = opts.resolution
        label = f"MISSING\\: {slot.slot_id}"
        vf = (
            f"drawtext=fontfile='{_FONT_FILE}':text='{label}':fontcolor=white:fontsize=48:"
            "x=(w-text_w)/2:y=(h-text_h)/2"
        )
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:d={slot.duration_s}:r=30",
            "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    def _concat_segments(self, segment_paths: list[Path], output_path: Path) -> None:
        concat_list_path = segment_paths[0].parent / "concat_list.txt"
        concat_list_path.write_text("".join(f"file '{p.as_posix()}'\n" for p in segment_paths))
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list_path),
            "-c", "copy", str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
