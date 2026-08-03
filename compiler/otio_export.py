"""
L3 - Template -> OpenTimelineIO (.otio) export. See RECUT_SPEC.md sec 5.3:
"this is your credibility feature for pro users" (opens directly in
Resolve/Premiere workflows).

SCOPE NOTE (DESIGN_NOTES.md "Defer OTIO, don't skip it"): do not build this
in Phase 1/2. It has no bearing on whether the core analysis or render
pipeline works, and building it early risks modeling OTIO's timeline
structure against a Template schema that's still churning. Build it once
template.v1 has stabilized (Phase 3+), against a fixed schema version.
"""

from __future__ import annotations

from pathlib import Path

from schemas.models import Template


def export_otio(template: Template, out_path: Path) -> None:
    raise NotImplementedError
