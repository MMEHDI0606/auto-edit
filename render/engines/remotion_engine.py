"""
PRIMARY render engine for this scaffold (see DESIGN_NOTES.md "Renderer
choice" - this is a deliberate deviation from the original spec's
recommendation of Revideo-as-primary).

Remotion is a Node/React renderer; this Python module is a thin adapter
that shells out to a Remotion Node worker (see render/effects_library/ for
the primitive library both engines share the CONTRACT for, even though
each implements it in its own runtime).

Licensing reminder (carried over from spec sec 7.1, still true regardless
of primary/secondary choice): Remotion requires a paid company license
above a headcount threshold. This is a budgeted business decision to
revisit before scaling revenue (see DESIGN_NOTES.md), not a blocker for
building against it now.
"""

from __future__ import annotations

from pathlib import Path

from render.interface import RenderEngine, RenderOptions, RenderReport
from schemas.models import BindingSet, Template


class RemotionEngine(RenderEngine):
    name = "remotion"

    def render(self, template: Template, bindings: BindingSet, opts: RenderOptions) -> RenderReport:
        """Serializes (template, bindings, opts) to the Remotion props JSON
        format (spec sec 5.3, interchange format #3) and invokes the Node
        worker (api/workers.py owns the subprocess/queue plumbing)."""
        raise NotImplementedError

    def preview(self, template: Template, bindings: BindingSet) -> Path:
        raise NotImplementedError
