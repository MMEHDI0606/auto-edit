import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {getEasingFunction} from "./easing";

export interface ScaleRampProps {
  from_scale: number;
  to_scale: number;
  easing: string;
  durationInFrames: number;
  children: React.ReactNode;
}

/**
 * Shared implementation behind PunchIn and SlowPush - both are scale
 * ramps with an identical parameter shape (schemas.models.MotionPrimitive
 * groups them the same way, see render/effects_library/primitives.py's
 * fallback table comment: "both are scale ramps"). Exported as two
 * distinct named components anyway per Unit 2.7's "one component per
 * PRIMITIVE_PARAM_CONTRACTS entry" instruction - PunchIn.tsx/SlowPush.tsx
 * are thin wrappers around this.
 */
export const ScaleRamp: React.FC<ScaleRampProps> = ({
  from_scale,
  to_scale,
  easing,
  durationInFrames,
  children,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  let scale: number;
  if (easing === "spring") {
    const progress = spring({frame, fps, durationInFrames, config: {damping: 12}});
    scale = from_scale + (to_scale - from_scale) * progress;
  } else {
    scale = interpolate(frame, [0, durationInFrames], [from_scale, to_scale], {
      easing: getEasingFunction(easing),
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }

  return (
    <div style={{width: "100%", height: "100%", transform: `scale(${scale})`, transformOrigin: "center center"}}>
      {children}
    </div>
  );
};

/** Exported for the interpolation-math unit tests - avoids re-deriving
 * the scale formula in the test file (which would just be a copy that
 * could silently drift from the real implementation). */
export function computeScaleRampValue(
  frame: number,
  from_scale: number,
  to_scale: number,
  easing: string,
  durationInFrames: number,
  fps: number,
): number {
  if (easing === "spring") {
    const progress = spring({frame, fps, durationInFrames, config: {damping: 12}});
    return from_scale + (to_scale - from_scale) * progress;
  }
  return interpolate(frame, [0, durationInFrames], [from_scale, to_scale], {
    easing: getEasingFunction(easing),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}
