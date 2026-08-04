import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import type {Flash as FlashProps} from "../primitiveTypes";

/** Triangular opacity spike: 0 -> 1 -> 0 across duration_f frames, peaking
 * at the midpoint. `t` is in SECONDS (matches signals/effects.py's
 * ShotEffect.params["t"]) and is relative to the shot, so it's converted
 * to a frame offset via fps here rather than expecting the caller to
 * pre-convert. */
export function computeFlashOpacity(frame: number, fps: number, t: number, duration_f: number): number {
  const flashStartFrame = t * fps;
  return interpolate(
    frame,
    [flashStartFrame, flashStartFrame + duration_f / 2, flashStartFrame + duration_f],
    [0, 1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );
}

export const Flash: React.FC<FlashProps & {children: React.ReactNode}> = ({t, duration_f, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = computeFlashOpacity(frame, fps, t, duration_f);
  return (
    <div style={{width: "100%", height: "100%", position: "relative"}}>
      {children}
      <div
        style={{position: "absolute", inset: 0, backgroundColor: "white", opacity, pointerEvents: "none"}}
      />
    </div>
  );
};
