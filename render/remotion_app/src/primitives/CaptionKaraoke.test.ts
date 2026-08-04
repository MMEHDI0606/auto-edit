import {describe, expect, it} from "vitest";
import {findActiveWordIndex} from "./CaptionKaraoke";
import type {TranscriptWord} from "../primitiveTypes";

const WORDS: TranscriptWord[] = [
  {t: 0.0, word: "hello", conf: 0.9},
  {t: 0.5, word: "there", conf: 0.9},
  {t: 1.2, word: "world", conf: 0.9},
];

describe("findActiveWordIndex", () => {
  it("returns -1 before the first word", () => {
    expect(findActiveWordIndex(-0.1, WORDS)).toBe(-1);
  });

  it("returns the first word's index right at its timestamp", () => {
    expect(findActiveWordIndex(0.0, WORDS)).toBe(0);
  });

  it("returns the correct word mid-way through its window", () => {
    expect(findActiveWordIndex(0.7, WORDS)).toBe(1);
  });

  it("returns the last word once past its timestamp, with no upper bound", () => {
    expect(findActiveWordIndex(5.0, WORDS)).toBe(2);
  });
});
