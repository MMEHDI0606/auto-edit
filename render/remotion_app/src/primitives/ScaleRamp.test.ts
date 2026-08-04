import {describe, expect, it} from "vitest";
import {computeScaleRampValue} from "./ScaleRamp";

describe("computeScaleRampValue", () => {
  it("equals from_scale at frame 0", () => {
    expect(computeScaleRampValue(0, 1.0, 1.2, "linear", 30, 30)).toBeCloseTo(1.0, 5);
  });

  it("equals to_scale at the final frame", () => {
    expect(computeScaleRampValue(30, 1.0, 1.2, "linear", 30, 30)).toBeCloseTo(1.2, 5);
  });

  it("is monotonically increasing across the ramp for linear easing", () => {
    const values = Array.from({length: 31}, (_, f) => computeScaleRampValue(f, 1.0, 1.2, "linear", 30, 30));
    for (let i = 1; i < values.length; i++) {
      expect(values[i]).toBeGreaterThanOrEqual(values[i - 1]);
    }
  });

  it("clamps before frame 0 and after the final frame", () => {
    expect(computeScaleRampValue(-5, 1.0, 1.2, "linear", 30, 30)).toBeCloseTo(1.0, 5);
    expect(computeScaleRampValue(100, 1.0, 1.2, "linear", 30, 30)).toBeCloseTo(1.2, 5);
  });

  it("easeOut reaches to_scale faster than linear at the midpoint (decelerating into the target)", () => {
    const linearMid = computeScaleRampValue(15, 1.0, 1.2, "linear", 30, 30);
    const easeOutMid = computeScaleRampValue(15, 1.0, 1.2, "easeOut", 30, 30);
    expect(easeOutMid).toBeGreaterThan(linearMid);
  });

  it("spring easing starts at from_scale and ends near to_scale", () => {
    expect(computeScaleRampValue(0, 1.0, 1.2, "spring", 30, 30)).toBeCloseTo(1.0, 3);
    expect(computeScaleRampValue(60, 1.0, 1.2, "spring", 30, 30)).toBeCloseTo(1.2, 1);
  });
});
