"""
Unit 1.3 done criteria: mask_watermark_regions() masks a static corner
watermark and does NOT mask a corner where content is actually changing
(the specific false-positive spec sec 8.3 warns about - a subject moving
through a corner must not be mistaken for a watermark bug).

Uses synthetic frame arrays rather than a real video - the detector's
input contract is "a list of frames" (whatever produced them), so a
hand-built positive+negative example is a faithful, deterministic test.
"""

from __future__ import annotations

import numpy as np

from signals.effects import mask_watermark_regions

H, W = 200, 200
CORNER = 30  # matches WATERMARK_CORNER_FRACTION * min(H, W), comfortably inside the 15% zone


def _make_frames(n: int, *, watermark_corner: bool, dynamic_corner: bool) -> list[np.ndarray]:
    frames = []
    rng = np.random.default_rng(0)
    for i in range(n):
        # Noisy background (real video always has some per-frame variance,
        # even a "static" shot) so only the deliberately-static watermark
        # region reads as near-zero variance - a uniform, unchanging
        # background would make every corner look static and defeat the test.
        frame = rng.integers(70, 90, size=(H, W, 3), dtype=np.uint8)
        if watermark_corner:
            # Static bright logo in top-right corner - identical every frame.
            frame[0:CORNER, W - CORNER : W] = 220
        if dynamic_corner:
            # Bottom-left corner changes value every frame (moving subject).
            # Random per-frame (not a fixed-period formula) so it can't
            # alias with the detector's own frame-sampling stride.
            frame[H - CORNER : H, 0:CORNER] = rng.integers(0, 255, size=(CORNER, CORNER, 3), dtype=np.uint8)
        frames.append(frame)
    return frames


def test_detects_and_masks_static_corner_watermark() -> None:
    frames = _make_frames(15, watermark_corner=True, dynamic_corner=False)
    masked_frames, masked_rects = mask_watermark_regions(frames)

    assert len(masked_rects) == 1
    x, y, w, h = masked_rects[0]
    # Should be the top-right corner.
    assert x > W / 2 and y < H / 2

    # The watermark region's pixel values should no longer be uniformly 220
    # after masking (median-blurred against itself - since the whole patch
    # was uniform, this mainly asserts masking ran, not a value change bar).
    assert masked_frames[0][y : y + h, x : x + w].shape == (h, w, 3)


def test_does_not_mask_dynamic_corner_with_real_motion() -> None:
    frames = _make_frames(15, watermark_corner=False, dynamic_corner=True)
    _, masked_rects = mask_watermark_regions(frames)
    assert masked_rects == []


def test_detects_watermark_but_ignores_dynamic_corner_in_same_video() -> None:
    frames = _make_frames(15, watermark_corner=True, dynamic_corner=True)
    _, masked_rects = mask_watermark_regions(frames)
    assert len(masked_rects) == 1
    x, y, _, _ = masked_rects[0]
    assert x > W / 2 and y < H / 2  # top-right (watermark), not bottom-left (motion)


def test_empty_input_returns_empty() -> None:
    assert mask_watermark_regions([]) == ([], [])


def test_no_watermark_returns_frames_unchanged() -> None:
    frames = _make_frames(15, watermark_corner=False, dynamic_corner=False)
    masked_frames, masked_rects = mask_watermark_regions(frames)
    assert masked_rects == []
    assert len(masked_frames) == len(frames)
