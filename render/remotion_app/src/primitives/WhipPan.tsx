import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import type {WhipPan as WhipPanProps} from "../primitiveTypes";

const DIRECTION_VECTORS: Record<string, [number, number]> = {
  left: [-1, 0],
  right: [1, 0],
  up: [0, -1],
  down: [0, 1],
};

const WHIP_MAGNITUDE_PX = 400; // approximate full-frame-width-ish displacement for the whip

export function computeWhipPanTranslate(
  frame: number,
  direction: string,
  duration_f: number,
): {translateX: number; translateY: number} {
  const [dx, dy] = DIRECTION_VECTORS[direction] ?? [0, 0];
  const progress = interpolate(frame, [0, duration_f], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return {translateX: dx * WHIP_MAGNITUDE_PX * progress, translateY: dy * WHIP_MAGNITUDE_PX * progress};
}

export const WhipPan: React.FC<WhipPanProps & {children: React.ReactNode}> = ({
  direction,
  duration_f,
  children,
}) => {
  const frame = useCurrentFrame();
  const {translateX, translateY} = computeWhipPanTranslate(frame, direction, duration_f);
  return (
    <div style={{width: "100%", height: "100%", transform: `translate(${translateX}px, ${translateY}px)`}}>
      {children}
    </div>
  );
};
