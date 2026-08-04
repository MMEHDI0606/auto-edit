import {describe, expect, it} from "vitest";
import {computeVisibleWordCount} from "./TextWordByWord";

describe("computeVisibleWordCount", () => {
  it("reveals 0 words at frame 0", () => {
    expect(computeVisibleWordCount(0, 0.5, 5)).toBe(0);
  });

  it("reveals words_per_f * frame words, floored", () => {
    expect(computeVisibleWordCount(4, 0.5, 5)).toBe(2);
  });

  it("never exceeds total word count", () => {
    expect(computeVisibleWordCount(1000, 0.5, 5)).toBe(5);
  });
});
