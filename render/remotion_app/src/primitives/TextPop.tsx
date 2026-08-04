import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import type {TextPop as TextPopProps} from "../primitiveTypes";

export function computeTextPopStyle(
  frame: number,
  in_duration_f: number,
): {scale: number; opacity: number} {
  const scale = interpolate(frame, [0, in_duration_f], [0.5, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame, [0, in_duration_f * 0.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return {scale, opacity};
}

export const TextPop: React.FC<TextPopProps & {children: React.ReactNode}> = ({in_duration_f, children}) => {
  const frame = useCurrentFrame();
  const {scale, opacity} = computeTextPopStyle(frame, in_duration_f);
  return <div style={{transform: `scale(${scale})`, opacity}}>{children}</div>;
};
