import {describe, expect, it} from "vitest";
import {computeFlashOpacity} from "./Flash";

describe("computeFlashOpacity", () => {
  const fps = 30;
  const t = 1.0; // flash at 1.0s -> frame 30
  const duration_f = 10;

  it("is zero before the flash starts", () => {
    expect(computeFlashOpacity(20, fps, t, duration_f)).toBeCloseTo(0, 5);
  });

  it("peaks at 1.0 at the midpoint of the flash", () => {
    const flashStartFrame = t * fps;
    expect(computeFlashOpacity(flashStartFrame + duration_f / 2, fps, t, duration_f)).toBeCloseTo(1.0, 5);
  });

  it("returns to zero after the flash ends", () => {
    const flashStartFrame = t * fps;
    expect(computeFlashOpacity(flashStartFrame + duration_f, fps, t, duration_f)).toBeCloseTo(0, 5);
    expect(computeFlashOpacity(flashStartFrame + duration_f + 20, fps, t, duration_f)).toBeCloseTo(0, 5);
  });

  it("is symmetric around the midpoint", () => {
    const flashStartFrame = t * fps;
    const before = computeFlashOpacity(flashStartFrame + 2, fps, t, duration_f);
    const after = computeFlashOpacity(flashStartFrame + duration_f - 2, fps, t, duration_f);
    expect(before).toBeCloseTo(after, 5);
  });
});
