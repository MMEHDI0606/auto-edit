import React from "react";
import {useCurrentFrame} from "remotion";
import type {TextTypewriter as TextTypewriterProps} from "../primitiveTypes";

/** `text` is not part of PRIMITIVE_PARAM_CONTRACTS (which only describes
 * animation-timing params) - it's the layer's own TextLayer.string,
 * supplied separately by the composition. */
export function computeVisibleChars(frame: number, chars_per_f: number, textLength: number): number {
  return Math.max(0, Math.min(textLength, Math.floor(frame * chars_per_f)));
}

export const TextTypewriter: React.FC<TextTypewriterProps & {text: string}> = ({chars_per_f, text}) => {
  const frame = useCurrentFrame();
  const visibleChars = computeVisibleChars(frame, chars_per_f, text.length);
  return <span>{text.slice(0, visibleChars)}</span>;
};
