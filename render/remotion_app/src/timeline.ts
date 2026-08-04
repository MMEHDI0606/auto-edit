import type {Slot, Template} from "./recutTypes";

export interface SlotFrameRange {
  slot: Slot;
  fromFrame: number;
  durationInFrames: number;
}

export function computeSlotFrameRanges(template: Template, fps: number): SlotFrameRange[] {
  let cumulativeFrame = 0;
  return template.slots.map((slot) => {
    const durationInFrames = Math.max(1, Math.round(slot.duration_s * fps));
    const range: SlotFrameRange = {slot, fromFrame: cumulativeFrame, durationInFrames};
    cumulativeFrame += durationInFrames;
    return range;
  });
}

export function computeTotalDurationInFrames(template: Template, fps: number): number {
  // Remotion's <Composition> throws if durationInFrames <= 0, even just to
  // list compositions with default (possibly empty-template) props before
  // real --props are supplied at render time - floor at 1 frame so an
  // empty/placeholder template never crashes composition discovery.
  const total = template.slots.reduce((sum, slot) => sum + Math.max(1, Math.round(slot.duration_s * fps)), 0);
  return Math.max(1, total);
}

/**
 * Mirrors render/effects_library/primitives.py::nearest_fallback_primitive's
 * table - kept in sync by hand (see that module's own comment about the
 * literal INSTRUCTIONS.md example not matching this scaffold's real data).
 * The TS side needs its own copy because the actual component resolution
 * happens at render time in Node, not by calling back into Python.
 */
const MOTION_COMPONENT_MAP: Record<string, string> = {
  punch_in: "punch_in",
  slow_push: "slow_push",
  zoom_out_reveal: "punch_in",
  pan: "whip_pan",
  whip: "whip_pan",
  static: "static",
  keyframed: "keyframed",
};

export function resolveMotionComponent(primitive: string): {component: string; wasFallback: boolean} {
  const resolved = MOTION_COMPONENT_MAP[primitive] ?? "static";
  return {component: resolved, wasFallback: resolved !== primitive};
}
