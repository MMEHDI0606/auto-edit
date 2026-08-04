import React from "react";
import {useCurrentFrame} from "remotion";
import type {TextWordByWord as TextWordByWordProps} from "../primitiveTypes";

export function computeVisibleWordCount(frame: number, words_per_f: number, totalWords: number): number {
  return Math.max(0, Math.min(totalWords, Math.floor(frame * words_per_f)));
}

export const TextWordByWord: React.FC<TextWordByWordProps & {text: string}> = ({words_per_f, text}) => {
  const frame = useCurrentFrame();
  const words = text.split(" ");
  const visibleWordCount = computeVisibleWordCount(frame, words_per_f, words.length);
  return <span>{words.slice(0, visibleWordCount).join(" ")}</span>;
};
