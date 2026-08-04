import React from "react";
import {Sequence} from "remotion";
import type {SpeedRamp as SpeedRampProps} from "../primitiveTypes";

/**
 * Approximates a speed ramp as 2-3 piecewise-CONSTANT playback rates
 * (matches signals/effects.py::detect_speed_ramp's own piecewise-linear
 * approximation of motion magnitude - the source signal is already an
 * approximation, so a further "smooth ramp between rates" here would be
 * false precision). Splits into one <Sequence> per segment and hands each
 * segment's `rate` to the child render-prop, which is expected to apply
 * it as the underlying <OffthreadVideo playbackRate={rate}>.
 */
export const SpeedRamp: React.FC<
  SpeedRampProps & {fps: number; children: (playbackRate: number) => React.ReactNode}
> = ({segments, fps, children}) => {
  return (
    <>
      {segments.map((segment, i) => {
        const fromFrame = Math.round(segment.t_in * fps);
        const durationInFrames = Math.max(1, Math.round((segment.t_out - segment.t_in) * fps));
        return (
          <Sequence key={i} from={fromFrame} durationInFrames={durationInFrames}>
            {children(segment.rate)}
          </Sequence>
        );
      })}
    </>
  );
};
