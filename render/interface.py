"""
L5 - the render engine interface. This file did not exist as a distinct
artifact in the original spec's repo layout (sec 13 just listed
`revideo/ remotion/ effects_library/` as sibling directories with no
abstraction boundary called out) - see DESIGN_NOTES.md "Renderer choice"
for why this interface is worth having explicitly and why this scaffold
defaults to Remotion as the primary engine rather than Revideo.

Every engine adapter (engines/remotion_engine.py, engines/revideo_engine.py,
engines/ffmpeg_engine.py) implements RenderEngine. compiler/template.py and
matcher/assign.py output must be fully consumable through BindingSet alone
- an engine implementation must never need to reach back into the trace or
re-derive anything the template/bindings didn't already carry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from schemas.models import BindingSet, Template


@dataclass
class RenderOptions:
    include_audio: bool = False  # see AudioRef.embed_permitted - default False
    resolution: tuple[int, int] = (1080, 1920)
    # Gap found during Unit 2.5 (ffmpeg engine): the interface had no way
    # for a caller to say where the output should go - every engine
    # defaulted to inventing its own temp path. None = engine picks a temp
    # path and returns it via RenderReport.output_path.
    output_path: Path | None = None


@dataclass
class RenderReport:
    """Every approximation made during render, surfaced to the user per
    spec sec 7.3 ("ship the render report so the user knows exactly what
    was approximated"). Must include everything already flagged in
    Template.confidence_flags PLUS any degradation the engine itself had
    to apply (e.g. "no library primitive for X, used nearest match Y")."""

    approximations: list[str]
    output_path: Path


class RenderEngine(ABC):
    name: str  # "remotion" | "revideo" | "ffmpeg"

    @abstractmethod
    def render(self, template: Template, bindings: BindingSet, opts: RenderOptions) -> RenderReport:
        ...

    @abstractmethod
    def preview(self, template: Template, bindings: BindingSet) -> Path:
        """Storyboard PNG or short GIF - fast iteration path, spec sec 7.3."""


def get_engine(name: str) -> RenderEngine:
    """Factory. `name` should come from common.config.Settings.
    primary_render_engine unless the caller explicitly overrides (e.g. MCP
    tool param, spec sec 9.3 recut.render future extension).

    Imports engine modules lazily (inside the function body) rather than
    at module level - render/interface.py is imported BY every engine
    module, so a top-level import here would be circular.
    """
    from render.engines.ffmpeg_engine import FfmpegEngine
    from render.engines.remotion_engine import RemotionEngine
    from render.engines.revideo_engine import RevideoEngine

    engines: dict[str, type[RenderEngine]] = {
        "ffmpeg": FfmpegEngine,
        "remotion": RemotionEngine,
        "revideo": RevideoEngine,
    }
    engine_cls = engines.get(name)
    if engine_cls is None:
        raise ValueError(f"Unknown render engine {name!r}, expected one of {sorted(engines)}")
    return engine_cls()
