/**
 * Wire-format types mirroring schemas/models.py's Template/BindingSet
 * exactly as Pydantic's default `.model_dump()` produces them - snake_case
 * field names, `in_` (NOT the aliased "in") for TextLayerAnimation, since
 * the Python bridge (remotion_engine.py) calls plain model_dump() without
 * by_alias=True. Keep this file in sync by hand when schemas/models.py
 * changes - there is no automatic sync step (see Unit 2.7's own note:
 * "keep snake_case end-to-end or write one explicit, tested conversion
 * function, not an ad hoc one" - this project chose "keep snake_case
 * end-to-end," so this file just needs to track the Python side, no
 * conversion function needed at all).
 */

export interface MotionCurve {
  primitive: string;
  from_scale: number;
  to_scale: number;
  pan_tx: number;
  pan_ty: number;
  easing: string;
  residual: number;
  raw_keyframes: Array<Record<string, unknown>> | null;
}

export interface DurationFlex {
  min_s: number;
  max_s: number;
  snap: string;
}

export interface SlotRequirements {
  orientation: string;
  shot_type_pref: string[];
  needs_face: boolean;
  motion_pref: string | null;
  role: string | null;
}

export interface ShotEffect {
  type: string;
  params: Record<string, unknown>;
  confidence: number;
}

export interface SlotApplied {
  motion: MotionCurve;
  grade_ref: string | null;
  out_transition: string | null;
  effects: ShotEffect[];
}

export interface Slot {
  slot_id: string;
  order: number;
  duration_s: number;
  duration_flex: DurationFlex;
  requirements: SlotRequirements;
  applied: SlotApplied;
  human_instruction: string;
}

export interface AudioRef {
  platform: string | null;
  track_title: string | null;
  artist: string | null;
  start_offset_s: number;
  beat_grid_s: number[];
  embed_permitted: false;
}

export interface TextStyle {
  font_guess: string | null;
  font_confidence: number;
  fill: string | null;
  stroke: string | null;
  stroke_px: number;
  size_rel: number;
  has_background_pill: boolean;
}

export interface TextBox {
  x: number;
  y: number;
  w: number;
  anchor: string;
}

export interface TextLayerAnimation {
  in_: string;
  out: string;
  in_duration_f: number;
}

export interface TextLayer {
  id: string;
  t_in: number;
  t_out: number;
  string: string;
  role: string;
  role_confidence: number;
  box: TextBox;
  style: TextStyle;
  animation: TextLayerAnimation;
}

export interface Template {
  template_version: string;
  source_trace_hash: string;
  slots: Slot[];
  audio_ref: AudioRef;
  text_layers: TextLayer[];
  confidence_flags: string[];
}

export interface AssetBinding {
  slot_id: string;
  asset_id: string;
  in_point_s: number;
  confidence: number;
  rationale: string;
}

export interface BindingSet {
  binding_id: string;
  template_version: string;
  bindings: AssetBinding[];
  unresolved_slots: string[];
}

export interface RenderOpts {
  include_audio: boolean;
  resolution: [number, number];
}

// `type`, not `interface`, deliberately: Remotion's <Composition> generic
// is constrained to Record<string, unknown>, which an `interface` doesn't
// structurally satisfy (TS2344 "Index signature for type 'string' is
// missing") - only a `type` alias for a plain object shape does. This is
// the one type in this file that's used directly as that generic
// argument, so it's the only one that needs the fix.
export type RecutEditProps = {
  template: Template;
  bindings: BindingSet;
  opts: RenderOpts;
};
