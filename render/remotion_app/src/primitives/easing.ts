import {Easing} from "remotion";

/**
 * Maps RECUT's Easing enum (schemas.models.Easing: linear/easeIn/easeOut/
 * easeInOut/spring) to Remotion's built-in easing curves. "spring" is NOT
 * handled here - it uses Remotion's dedicated spring() physics function
 * at the call site instead of an Easing curve (a real spring has
 * momentum/overshoot an Easing curve can't express), so this function is
 * never called with "spring" in practice; the branch exists only as a
 * safe fallback if it somehow is.
 *
 * easeIn/easeOut map to quad (matches signals/motion.py's Python-side fit
 * functions exactly: t**2 for easeIn, 1-(1-t)**2 for easeOut - both
 * quadratic). easeInOut maps to quad too, though the Python side uses a
 * cubic smoothstep (t*t*(3-2t)) - close enough in shape that a dedicated
 * cubic Easing curve isn't worth the extra indirection; documented here
 * as an approximation, not an exact match.
 */
export function getEasingFunction(easing: string): (input: number) => number {
  switch (easing) {
    case "linear":
      return Easing.linear;
    case "easeIn":
      return Easing.in(Easing.quad);
    case "easeOut":
      return Easing.out(Easing.quad);
    case "easeInOut":
      return Easing.inOut(Easing.quad);
    case "spring":
      return Easing.out(Easing.quad);
    default:
      return Easing.linear;
  }
}
