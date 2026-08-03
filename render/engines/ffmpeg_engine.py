"""
Fallback engine for cut-only templates (no kinetic text, no complex
motion). Fastest, poorest for kinetic text - spec sec 7.1. Useful as the
Phase-1/2 smoke-test engine since it has no Node dependency at all; wire
this up FIRST if you want an end-to-end (trace -> template -> rendered
MP4) smoke test before RemotionEngine exists.
"""

from __future__ import annotations

from pathlib import Path

from render.interface import RenderEngine, RenderOptions, RenderReport
from schemas.models import BindingSet, Template


class FfmpegEngine(RenderEngine):
    name = "ffmpeg"

    def render(self, template: Template, bindings: BindingSet, opts: RenderOptions) -> RenderReport:
        """Builds an ffmpeg filtergraph directly from bindings + cut points.
        No text animation, no kinetic effects - degrade every text layer to
        a static overlay and record that degradation in RenderReport.
        """
        raise NotImplementedError

    def preview(self, template: Template, bindings: BindingSet) -> Path:
        raise NotImplementedError
