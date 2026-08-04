import {describe, expect, it} from "vitest";
import {computeShakeOffset} from "./Shake";

describe("computeShakeOffset", () => {
  it("is zero at frame 0 (sin(0)=0, but cos(0)=1 for Y - only X starts at zero)", () => {
    const {dx} = computeShakeOffset(0, 30, 5.0, 8.0);
    expect(dx).toBeCloseTo(0, 5);
  });

  it("stays within +/- amplitude_px on both axes", () => {
    const amplitude = 6.0;
    for (let frame = 0; frame < 60; frame++) {
      const {dx, dy} = computeShakeOffset(frame, 30, amplitude, 9.0);
      expect(Math.abs(dx)).toBeLessThanOrEqual(amplitude + 1e-9);
      expect(Math.abs(dy)).toBeLessThanOrEqual(amplitude + 1e-9);
    }
  });

  it("oscillates rather than staying constant across many frames", () => {
    const values = Array.from({length: 30}, (_, f) => computeShakeOffset(f, 30, 5.0, 8.0).dx);
    const distinctSigns = new Set(values.map((v) => Math.sign(v)));
    expect(distinctSigns.size).toBeGreaterThan(1);
  });

  it("zero amplitude means zero offset regardless of frame", () => {
    // 0 * sin(...) can produce JS's -0 (equal to 0 under == and +, distinct
    // under Object.is) - assert numeric equality, not sign-of-zero identity.
    const {dx, dy} = computeShakeOffset(15, 30, 0, 8.0);
    expect(dx === 0).toBe(true);
    expect(dy === 0).toBe(true);
  });
});
