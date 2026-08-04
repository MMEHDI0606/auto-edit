import {describe, expect, it} from "vitest";
import {computeVisibleChars} from "./TextTypewriter";

describe("computeVisibleChars", () => {
  it("reveals 0 characters at frame 0", () => {
    expect(computeVisibleChars(0, 2, 20)).toBe(0);
  });

  it("reveals chars_per_f * frame characters, floored", () => {
    expect(computeVisibleChars(5, 2, 20)).toBe(10);
    expect(computeVisibleChars(5, 1.5, 20)).toBe(7); // floor(7.5)
  });

  it("never exceeds the text length", () => {
    expect(computeVisibleChars(1000, 2, 20)).toBe(20);
  });
});
