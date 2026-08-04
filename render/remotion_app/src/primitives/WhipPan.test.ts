import {describe, expect, it} from "vitest";
import {computeWhipPanTranslate} from "./WhipPan";

describe("computeWhipPanTranslate", () => {
  it("is zero displacement at frame 0", () => {
    const {translateX, translateY} = computeWhipPanTranslate(0, "left", 10);
    expect(translateX).toBeCloseTo(0, 5);
    expect(translateY).toBeCloseTo(0, 5);
  });

  it("moves negative X for left, positive X for right", () => {
    const left = computeWhipPanTranslate(10, "left", 10);
    const right = computeWhipPanTranslate(10, "right", 10);
    expect(left.translateX).toBeLessThan(0);
    expect(right.translateX).toBeGreaterThan(0);
  });

  it("moves along Y only for up/down, leaving X at zero", () => {
    const up = computeWhipPanTranslate(10, "up", 10);
    expect(up.translateX).toBeCloseTo(0, 5);
    expect(up.translateY).toBeLessThan(0);
  });

  it("clamps beyond duration_f", () => {
    const atEnd = computeWhipPanTranslate(10, "left", 10);
    const wayPast = computeWhipPanTranslate(1000, "left", 10);
    expect(wayPast.translateX).toBeCloseTo(atEnd.translateX, 5);
  });

  it("unknown direction produces zero displacement, not a crash", () => {
    const {translateX, translateY} = computeWhipPanTranslate(5, "diagonal", 10);
    expect(translateX).toBe(0);
    expect(translateY).toBe(0);
  });
});
