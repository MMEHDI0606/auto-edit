"""
L3 orchestrator - Trace (+ optional SemanticAnnotations) -> Template.
See RECUT_SPEC.md sec 5.

This is the only compiler/ entry point other packages should import.
"""

from __future__ import annotations

from schemas.models import EditTrace, SemanticAnnotations, Template


def compile_template(trace: EditTrace, *, semantics: SemanticAnnotations | None = None) -> Template:
    """Builds slots (compiler.slots.shot_to_slot per shot), builds the
    AudioRef (never an embedded file - see schemas.models.AudioRef and
    DESIGN_NOTES.md "Rights posture"), and collects confidence_flags from
    every low-confidence estimate encountered (font guesses, speed-ramp
    linearization, grade-not-applied, etc) so render/ can surface them in
    the render report (spec sec 7.3).
    """
    raise NotImplementedError
