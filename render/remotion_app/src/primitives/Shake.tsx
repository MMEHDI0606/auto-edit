import React from "react";
import {useCurrentFrame, useVideoConfig} from "remotion";
import type {Shake as ShakeProps} from "../primitiveTypes";

/** Y axis uses a slightly different frequency multiplier (1.3x) than X so
 * the jitter reads as irregular handheld shake rather than a pure
 * diagonal oscillation - a real handheld shake isn't perfectly circular. */
export function computeShakeOffset(
  frame: number,
  fps: number,
  amplitude_px: number,
  freq_hz: number,
): {dx: number; dy: number} {
  const t = frame / fps;
  const dx = amplitude_px * Math.sin(2 * Math.PI * freq_hz * t);
  const dy = amplitude_px * Math.cos(2 * Math.PI * freq_hz * 1.3 * t);
  return {dx, dy};
}

export const Shake: React.FC<ShakeProps & {children: React.ReactNode}> = ({
  amplitude_px,
  freq_hz,
  children,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {dx, dy} = computeShakeOffset(frame, fps, amplitude_px, freq_hz);
  return (
    <div style={{width: "100%", height: "100%", transform: `translate(${dx}px, ${dy}px)`}}>{children}</div>
  );
};
