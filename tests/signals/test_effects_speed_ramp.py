"""
Unit 1.14 done criteria: detect_speed_ramp() fires on an obvious case
(motion rate discontinuity WITH a corresponding audio pitch shift) and
does not fire on constant-speed shots. No numeric accuracy target per
INSTRUCTIONS.md - "fires on the obvious cases, doesn't fire on
constant-speed shots" is the whole bar.
"""

from __future__ import annotations

from signals.effects import SPEED_RAMP_CONFIDENCE, detect_speed_ramp


def test_fires_on_motion_discontinuity_with_matching_pitch_shift() -> None:
    # Slow motion for 10 frames, then abruptly much faster for 10 frames -
    # a clear piecewise-linear discontinuity a single line can't explain.
    motion = [1.0] * 10 + [8.0] * 10
    # Pitch shifts at the same relative point - the "played back faster"
    # signature of a real speed ramp.
    pitch = [200.0] * 10 + [260.0] * 10

    effect = detect_speed_ramp(motion, pitch)

    assert effect is not None
    assert effect.type.value == "speed_ramp"
    assert effect.confidence == SPEED_RAMP_CONFIDENCE
    assert effect.confidence < 1.0
    segments = effect.params["segments"]
    assert len(segments) >= 2
    assert segments[0]["t_in"] == 0


def test_none_for_constant_speed_shot() -> None:
    motion = [3.0 + 0.01 * i for i in range(20)]  # near-constant, tiny linear drift only
    pitch = [220.0] * 20
    assert detect_speed_ramp(motion, pitch) is None


def test_none_when_motion_jumps_but_pitch_does_not_shift() -> None:
    # A real motion discontinuity (e.g. a whip pan or sudden subject
    # movement) with NO corresponding pitch shift must NOT be called a
    # speed ramp - a true ramp changes both together.
    motion = [1.0] * 10 + [8.0] * 10
    pitch = [220.0] * 20  # flat - no pitch shift anywhere
    assert detect_speed_ramp(motion, pitch) is None


def test_none_without_pitch_series() -> None:
    motion = [1.0] * 10 + [8.0] * 10
    assert detect_speed_ramp(motion, []) is None


def test_none_for_too_short_series() -> None:
    assert detect_speed_ramp([1.0, 2.0], [200.0, 210.0]) is None
