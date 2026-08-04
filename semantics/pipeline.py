"""
Unit 3.4 - deep-pass trigger policy. Deliberately lives here (the semantics
package's top-level orchestration), NOT inside AnthropicProvider or any
other SemanticProvider implementation: a provider only knows how to RUN one
deep pass when asked; deciding WHICH shots are worth the slower, costlier
per-shot call is a policy decision independent of which provider is behind
it, and must not be duplicated per-provider.
"""

from __future__ import annotations

from schemas.models import Shot
from signals.motion import FIT_RESIDUAL_THRESHOLD  # reused, not reimplemented - Unit 1.6's own keyframe threshold


def needs_deep_pass(shot: Shot, *, needs_role_label: bool = False) -> bool:
    """True only where L1 confidence is genuinely low - motion fit fell
    back to raw keyframes (residual above the same threshold that triggers
    that fallback in signals/motion.py), or content labeling never ran -
    OR the compiler wants a role label for this shot (spec sec 4.2).
    Never call deep_pass() unconditionally; that defeats the two-pass cost
    structure the triage/deep-pass split exists for.
    """
    if shot.motion.residual > FIT_RESIDUAL_THRESHOLD:
        return True
    if shot.content.shot_type is None:
        return True
    return needs_role_label
