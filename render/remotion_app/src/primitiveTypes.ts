/**
 * TypeScript mirror of render/effects_library/primitives.py's
 * PRIMITIVE_PARAM_CONTRACTS, kept 1:1 with that dict (see Unit 2.7 in
 * INSTRUCTIONS.md - "treat that dict as the literal TypeScript prop-type
 * source"). Field names stay snake_case to match Pydantic's model_dump()
 * output exactly - do not camelCase these, the Python bridge passes props
 * straight through without a conversion step.
 *
 * A few components need one prop beyond their PRIMITIVE_PARAM_CONTRACTS
 * entry to actually render (e.g. TextTypewriter needs the literal string
 * to reveal, not just the reveal rate) - those extra fields are not part
 * of the contract itself (which only describes ANIMATION TIMING params);
 * they're supplied separately by the composition from TextLayer.string.
 */

export interface PunchIn {
  from_scale: number;
  to_scale: number;
  easing: string;
}

export interface SlowPush {
  from_scale: number;
  to_scale: number;
  easing: string;
}

export interface WhipPan {
  direction: string;
  duration_f: number;
}

export interface Shake {
  amplitude_px: number;
  freq_hz: number;
}

export interface Flash {
  t: number;
  duration_f: number;
}

export interface RgbSplit {
  offset_px_r: number;
  offset_px_b: number;
}

export interface Freeze {
  duration_f: number;
}

export interface SpeedRampSegment {
  t_in: number;
  t_out: number;
  rate: number;
}

export interface SpeedRamp {
  segments: SpeedRampSegment[];
}

export interface TextPop {
  in_duration_f: number;
}

export interface TextTypewriter {
  chars_per_f: number;
}

export interface TextWordByWord {
  words_per_f: number;
}

export interface TranscriptWord {
  t: number;
  word: string;
  conf: number;
}

export interface CaptionKaraoke {
  transcript_words: TranscriptWord[];
}
