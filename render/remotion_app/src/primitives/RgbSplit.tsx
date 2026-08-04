import React from "react";
import type {RgbSplit as RgbSplitProps} from "../primitiveTypes";

/**
 * Approximates chromatic-aberration/glitch by rendering the same content
 * three times, each isolated to one color channel via an SVG
 * feColorMatrix filter and offset by the detected per-channel pixel
 * displacement (signals/effects.py::detect_rgb_split's offset_px_r/
 * offset_px_b), then composited with mix-blend-mode: screen (which sums
 * light - reconstructing the original exactly where offsets are zero).
 * This is a visual approximation, not a physically exact channel split;
 * documented here per Unit 2.7's own note that this primitive's
 * implementation is a judgment call, not a specified algorithm.
 */
export const RgbSplit: React.FC<RgbSplitProps & {children: React.ReactNode}> = ({
  offset_px_r,
  offset_px_b,
  children,
}) => {
  return (
    <div style={{width: "100%", height: "100%", position: "relative"}}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translateX(${offset_px_r}px)`,
          mixBlendMode: "screen",
          filter: "url(#recut-red-channel)",
        }}
      >
        {children}
      </div>
      <div style={{position: "absolute", inset: 0, mixBlendMode: "screen", filter: "url(#recut-green-channel)"}}>
        {children}
      </div>
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translateX(${offset_px_b}px)`,
          mixBlendMode: "screen",
          filter: "url(#recut-blue-channel)",
        }}
      >
        {children}
      </div>
      <svg width="0" height="0" style={{position: "absolute"}}>
        <defs>
          <filter id="recut-red-channel">
            <feColorMatrix type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
          </filter>
          <filter id="recut-green-channel">
            <feColorMatrix type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" />
          </filter>
          <filter id="recut-blue-channel">
            <feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" />
          </filter>
        </defs>
      </svg>
    </div>
  );
};
