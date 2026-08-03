"""
SECONDARY render engine (spec's original primary recommendation, kept as
the licence-clean fallback - see DESIGN_NOTES.md "Renderer choice").

STUB ONLY for this scaffold: implement after RemotionEngine is proven on
the golden set (Phase 2), specifically if/when the Remotion licence cost
becomes a real business constraint, or if Remotion's kinetic-text ecosystem
turns out not to matter as much as expected for a given template class.
Keep the RenderEngine interface identical so swapping primary<->secondary
is a one-line config change (common.config.Settings.primary_render_engine),
never a call-site change.
"""

from __future__ import annotations

from pathlib import Path

from render.interface import RenderEngine, RenderOptions, RenderReport
from schemas.models import BindingSet, Template


class RevideoEngine(RenderEngine):
    name = "revideo"

    def render(self, template: Template, bindings: BindingSet, opts: RenderOptions) -> RenderReport:
        raise NotImplementedError

    def preview(self, template: Template, bindings: BindingSet) -> Path:
        raise NotImplementedError
