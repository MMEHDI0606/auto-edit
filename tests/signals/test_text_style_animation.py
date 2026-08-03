"""
Unit 1.8 done criteria: classify_entrance_exit() against synthetic bbox/
alpha tracks for each animation type, and extract_text_style() against a
synthetic frame with a real rendered glyph (cv2.putText) - not a real
video, since these operate on isolated frames/tracks, not a decoded clip.
"""

from __future__ import annotations

import cv2
import numpy as np

from signals.text import classify_entrance_exit, extract_text_style


def _track(boxes: list[tuple[float, float, float, float]], alphas: list[float] | None = None) -> list[dict]:
    alphas = alphas or [1.0] * len(boxes)
    return [{"box": b, "alpha": a} for b, a in zip(boxes, alphas)]


def test_classify_pop_entrance() -> None:
    # Rapidly grows in the first 3 frames then holds steady.
    boxes = [
        (0.4, 0.4, 0.05, 0.02),
        (0.4, 0.4, 0.08, 0.035),
        (0.4, 0.4, 0.1, 0.045),
        (0.4, 0.4, 0.1, 0.045),
        (0.4, 0.4, 0.1, 0.045),
        (0.4, 0.4, 0.1, 0.045),
    ]
    in_anim, _out_anim, in_duration = classify_entrance_exit(_track(boxes))
    assert in_anim == "pop"
    assert in_duration == len(boxes)


def test_classify_slide_up_entrance() -> None:
    # y decreases monotonically, x/size held constant.
    boxes = [(0.4, 0.9 - 0.05 * i, 0.2, 0.05) for i in range(8)]
    in_anim, _out_anim, _dur = classify_entrance_exit(_track(boxes))
    assert in_anim == "slide_up"


def test_classify_bounce_entrance() -> None:
    ys = [0.6, 0.5, 0.65, 0.48, 0.7, 0.55, 0.5, 0.5]
    boxes = [(0.4, y, 0.2, 0.05) for y in ys]
    in_anim, _out_anim, _dur = classify_entrance_exit(_track(boxes))
    assert in_anim == "bounce"


def test_classify_fade_entrance() -> None:
    boxes = [(0.4, 0.4, 0.2, 0.05)] * 6
    alphas = [0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
    in_anim, _out_anim, _dur = classify_entrance_exit(_track(boxes, alphas))
    assert in_anim == "fade"


def test_classify_defaults_to_fade_when_ambiguous() -> None:
    # Random/inconsistent motion with no clear pattern.
    boxes = [(0.4, 0.41, 0.2, 0.051), (0.41, 0.4, 0.199, 0.049)]
    in_anim, out_anim, _dur = classify_entrance_exit(_track(boxes))
    assert in_anim == "fade"
    assert out_anim == "fade"


def test_classify_entrance_exit_empty_input() -> None:
    assert classify_entrance_exit([]) == ("fade", "fade", 0)


def _frame_with_text(text: str = "HI", pill: bool = False) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    h, w = 200, 400
    frame = np.full((h, w, 3), 40, dtype=np.uint8)  # dark neutral background
    org = (100, 120)
    if pill:
        # Must fully contain the text bbox below (60,70)-(260,160) with
        # margin on all sides - a real pill is drawn to comfortably contain
        # its text, not tightly crop it.
        cv2.rectangle(frame, (40, 50), (290, 180), (10, 10, 200), -1)  # solid red pill behind text
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4, cv2.LINE_AA)
    # bbox roughly covering the rendered text
    box = (60 / w, 70 / h, 200 / w, 90 / h)
    return frame, box


def test_extract_text_style_detects_white_fill() -> None:
    frame, box = _frame_with_text()
    style = extract_text_style(frame, box)
    # fill should be near-white (the glyph color), not the dark background.
    r = int(style.fill[1:3], 16)
    g = int(style.fill[3:5], 16)
    b = int(style.fill[5:7], 16)
    assert (r + g + b) / 3 > 150


def test_extract_text_style_detects_background_pill() -> None:
    frame, box = _frame_with_text(pill=True)
    style = extract_text_style(frame, box)
    assert style.has_background_pill is True


def test_extract_text_style_no_pill_on_plain_background() -> None:
    frame, box = _frame_with_text(pill=False)
    style = extract_text_style(frame, box)
    assert style.has_background_pill is False


def test_extract_text_style_size_rel_matches_box_height() -> None:
    frame, box = _frame_with_text()
    style = extract_text_style(frame, box)
    assert style.size_rel == box[3]
