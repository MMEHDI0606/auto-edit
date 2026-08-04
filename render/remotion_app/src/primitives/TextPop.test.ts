import {describe, expect, it} from "vitest";
import {computeTextPopStyle} from "./TextPop";

describe("computeTextPopStyle", () => {
  it("starts small and transparent at frame 0", () => {
    const {scale, opacity} = computeTextPopStyle(0, 10);
    expect(scale).toBeCloseTo(0.5, 5);
    expect(opacity).toBeCloseTo(0, 5);
  });

  it("reaches full scale and opacity by in_duration_f", () => {
    const {scale, opacity} = computeTextPopStyle(10, 10);
    expect(scale).toBeCloseTo(1.0, 5);
    expect(opacity).toBeCloseTo(1.0, 5);
  });

  it("opacity reaches 1 before scale finishes growing (pops in fast, settles slower)", () => {
    const at6 = computeTextPopStyle(6, 10);
    expect(at6.opacity).toBeCloseTo(1.0, 5);
    expect(at6.scale).toBeLessThan(1.0);
  });
});
