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

import functools
import http.server
import json
import shutil
import socketserver
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from render.effects_library.primitives import nearest_fallback_primitive
from render.interface import RenderEngine, RenderOptions, RenderReport
from render.report import add_approximation
from schemas.models import AssetBinding, BindingSet, EffectType, Template

_REMOTION_APP_DIR = Path(__file__).resolve().parent.parent / "remotion_app"
_ENTRY_POINT = "src/index.ts"
_COMPOSITION_ID = "RecutEdit"

# EffectTypes with NO entry in render/effects_library/primitives.py's
# PRIMITIVE_PARAM_CONTRACTS at all (never did, in either language) - the
# TS composition silently skips these (see RecutEdit.tsx's wrapWithEffects
# docstring); this is where that gap gets surfaced to the user.
_UNSUPPORTED_EFFECT_TYPES = {EffectType.blur_pulse, EffectType.overlay_grain, EffectType.mask_cutout}


def _resolve_npx() -> str:
    """`subprocess.run(["npx", ...])` without shell=True fails on Windows
    with WinError 2 ("cannot find the file specified") - npx is npx.cmd, a
    batch-file shim, and Win32 CreateProcess doesn't resolve .cmd files via
    PATH the way a real .exe is resolved. shutil.which() correctly checks
    PATHEXT and returns the actual npx.cmd path, which then works fine in
    list-argument form - no shell=True (and its injection surface) needed."""
    npx_path = shutil.which("npx")
    if npx_path is None:
        raise RuntimeError("npx not found on PATH - Node.js/npm must be installed to use RemotionEngine")
    return npx_path


@contextmanager
def _staged_bindings_over_http(bindings: BindingSet):
    """Bound assets (AssetBinding.asset_id) are arbitrary local files
    wherever the user's footage lives, not bundled into remotion_app's
    public/ folder. Two direct approaches were tried against a real render
    and both failed for real (not hypothetical) reasons:
      - <OffthreadVideo src={absolute_path}>: its frame-extraction proxy
        only accepts http(s):// sources; a raw path auto-converts to
        file:// and the proxy rejects it outright.
      - <Video src={absolute_path}> with Chromium's disable-web-security
        flag set: headless Chrome's own <video> element still refused
        file:// media (net::ERR_UNKNOWN_URL_SCHEME) regardless.

    The actually-supported pattern: serve the assets over a real HTTP
    origin. This copies every bound asset into a throwaway staging
    directory, serves it via a short-lived local ThreadingHTTPServer, and
    yields a BindingSet whose asset_id fields are rewritten to
    http://127.0.0.1:PORT/... URLs - only for this render call, the
    caller's original BindingSet is never mutated.
    """
    with tempfile.TemporaryDirectory(prefix="recut_asset_stage_") as stage_dir:
        stage_path = Path(stage_dir)
        staged_bindings: list[AssetBinding] = []

        for binding in bindings.bindings:
            src_path = Path(binding.asset_id)
            staged_name = f"{binding.slot_id}{src_path.suffix}"
            shutil.copy2(src_path, stage_path / staged_name)
            staged_bindings.append((binding, staged_name))

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(stage_path))
        httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        try:
            rewritten = [
                binding.model_copy(update={"asset_id": f"http://127.0.0.1:{port}/{staged_name}"})
                for binding, staged_name in staged_bindings
            ]
            yield bindings.model_copy(update={"bindings": rewritten})
        finally:
            httpd.shutdown()
            httpd.server_close()


def _build_props(template: Template, bindings: BindingSet, opts: RenderOptions) -> dict:
    return {
        "template": template.model_dump(mode="json"),
        "bindings": bindings.model_dump(mode="json"),
        "opts": {"include_audio": opts.include_audio, "resolution": list(opts.resolution)},
    }


def _compute_approximations(template: Template) -> list[str]:
    """Approximations this engine's own substitutions cause, ON TOP OF
    Template.confidence_flags (already carried over from compile_template).
    Computed here in Python rather than round-tripped through a Node-side
    log file - resolveMotionComponent's fallback table
    (render/remotion_app/src/timeline.ts) is a hand-kept mirror of
    nearest_fallback_primitive(), so this reasons about exactly what the TS
    side will actually render without needing IPC to confirm it.
    """
    approximations = list(template.confidence_flags)

    for slot in template.slots:
        primitive_name = slot.applied.motion.primitive.value
        fallback = nearest_fallback_primitive(primitive_name)
        if fallback != primitive_name:
            add_approximation(approximations, slot.slot_id, f"{primitive_name} motion substituted with {fallback}")

        for effect in slot.applied.effects:
            if effect.type in _UNSUPPORTED_EFFECT_TYPES:
                add_approximation(
                    approximations, slot.slot_id, f"{effect.type.value} effect has no render primitive - not rendered"
                )

    return approximations


def _write_props_file(props: dict) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()) as f:
        json.dump(props, f)
        return Path(f.name)


class RemotionEngine(RenderEngine):
    name = "remotion"

    def render(self, template: Template, bindings: BindingSet, opts: RenderOptions) -> RenderReport:
        """Serializes (template, bindings, opts) to the Remotion props JSON
        format (spec sec 5.3, interchange format #3) and invokes the Node
        worker (api/workers.py owns the subprocess/queue plumbing)."""
        approximations = _compute_approximations(template)

        output_path = opts.output_path or Path(tempfile.mkdtemp(prefix="recut_remotion_")) / "render.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with _staged_bindings_over_http(bindings) as http_bindings:
            props = _build_props(template, http_bindings, opts)
            props_path = _write_props_file(props)
            try:
                subprocess.run(
                    [
                        _resolve_npx(), "remotion", "render", _ENTRY_POINT, _COMPOSITION_ID, str(output_path),
                        f"--props={props_path}",
                    ],
                    check=True, capture_output=True, text=True, cwd=_REMOTION_APP_DIR,
                )
            finally:
                props_path.unlink(missing_ok=True)

        return RenderReport(approximations=approximations, output_path=output_path)

    def preview(self, template: Template, bindings: BindingSet) -> Path:
        """Single still frame (the composition's first frame) via
        `remotion still` - not a full render. A simpler stand-in than
        FfmpegEngine's tiled multi-slot storyboard; a real per-slot
        storyboard would need one `still` invocation per slot's frame
        offset, which is straightforward to add later but not needed to
        prove this engine's Node bridge works end to end (this unit's
        stated bar - see INSTRUCTIONS.md Unit 2.7)."""
        opts = RenderOptions()
        output_path = Path(tempfile.mkdtemp(prefix="recut_remotion_preview_")) / "preview.png"

        with _staged_bindings_over_http(bindings) as http_bindings:
            props = _build_props(template, http_bindings, opts)
            props_path = _write_props_file(props)
            try:
                subprocess.run(
                    [
                        _resolve_npx(), "remotion", "still", _ENTRY_POINT, _COMPOSITION_ID, str(output_path),
                        f"--props={props_path}", "--frame=0",
                    ],
                    check=True, capture_output=True, text=True, cwd=_REMOTION_APP_DIR,
                )
            finally:
                props_path.unlink(missing_ok=True)

        return output_path
