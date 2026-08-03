"""
Unit 1.16 done criteria: grade_stats() numbers move in the expected
relative direction on visibly different grades - no absolute accuracy
bar, this is a relative signal per INSTRUCTIONS.md.
"""

from __future__ import annotations

import numpy as np

from signals.effects import grade_stats


def _flat_frame(bgr: tuple[int, int, int], size: int = 64) -> list:
    return [np.full((size, size, 3), bgr, dtype=np.uint8) for _ in range(5)]


def _noisy_frame(seed: int, size: int = 64, spread: int = 80) -> list:
    rng = np.random.default_rng(seed)
    base = 128
    frames = []
    for _ in range(5):
        frame = np.clip(
            base + rng.integers(-spread, spread, size=(size, size, 3)), 0, 255
        ).astype(np.uint8)
        frames.append(frame)
    return frames


def test_warm_shot_has_higher_temp_than_cool_shot() -> None:
    warm = _flat_frame((20, 20, 200))  # BGR: high red, low blue
    cool = _flat_frame((200, 20, 20))  # BGR: high blue, low red

    warm_grade = grade_stats(warm)
    cool_grade = grade_stats(cool)

    assert warm_grade.temp > cool_grade.temp
    assert warm_grade.temp > 0
    assert cool_grade.temp < 0


def test_higher_variance_shot_has_higher_contrast() -> None:
    punchy = _noisy_frame(seed=1, spread=100)
    flat = _flat_frame((128, 128, 128))

    assert grade_stats(punchy).contrast > grade_stats(flat).contrast


def test_grade_always_reports_no_lut() -> None:
    grade = grade_stats(_flat_frame((100, 100, 100)))
    assert grade.lut_available is False
    assert grade.lut_ref is None


def test_empty_input_returns_neutral_grade_with_no_lut() -> None:
    grade = grade_stats([])
    assert grade.lut_available is False
