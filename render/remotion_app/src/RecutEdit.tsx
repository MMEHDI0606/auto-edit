import React from "react";
import {AbsoluteFill, OffthreadVideo, Sequence, useVideoConfig} from "remotion";
import {Flash} from "./primitives/Flash";
import {Freeze} from "./primitives/Freeze";
import {PunchIn} from "./primitives/PunchIn";
import {RgbSplit} from "./primitives/RgbSplit";
import {Shake} from "./primitives/Shake";
import {SlowPush} from "./primitives/SlowPush";
import {SpeedRamp} from "./primitives/SpeedRamp";
import {TextPop} from "./primitives/TextPop";
import {TextTypewriter} from "./primitives/TextTypewriter";
import {TextWordByWord} from "./primitives/TextWordByWord";
import {WhipPan} from "./primitives/WhipPan";
import type {SpeedRampSegment} from "./primitiveTypes";
import type {AssetBinding, RecutEditProps, ShotEffect, Slot, TextLayer} from "./recutTypes";
import {computeSlotFrameRanges, resolveMotionComponent} from "./timeline";

const MissingSlot: React.FC<{slotId: string}> = ({slotId}) => (
  <AbsoluteFill style={{backgroundColor: "#444", alignItems: "center", justifyContent: "center"}}>
    <span style={{color: "white", fontSize: 32}}>MISSING: {slotId}</span>
  </AbsoluteFill>
);

/**
 * Resolves a slot's detected motion primitive to an available component
 * via the same fallback table as render/effects_library/primitives.py.
 * `whip_pan`'s direction isn't on MotionCurve (direction is a Transition-
 * level field, not a motion-curve field) - approximated here from the
 * dominant pan_tx/pan_ty axis, which is the only directional signal a
 * MotionCurve actually carries.
 */
const MotionWrapper: React.FC<{slot: Slot; durationInFrames: number; children: React.ReactNode}> = ({
  slot,
  durationInFrames,
  children,
}) => {
  const {component} = resolveMotionComponent(slot.applied.motion.primitive);
  const motion = slot.applied.motion;

  switch (component) {
    case "punch_in":
      return (
        <PunchIn
          from_scale={motion.from_scale}
          to_scale={motion.to_scale}
          easing={motion.easing}
          durationInFrames={durationInFrames}
        >
          {children}
        </PunchIn>
      );
    case "slow_push":
      return (
        <SlowPush
          from_scale={motion.from_scale}
          to_scale={motion.to_scale}
          easing={motion.easing}
          durationInFrames={durationInFrames}
        >
          {children}
        </SlowPush>
      );
    case "whip_pan": {
      const direction =
        Math.abs(motion.pan_tx) >= Math.abs(motion.pan_ty)
          ? motion.pan_tx >= 0
            ? "right"
            : "left"
          : motion.pan_ty >= 0
            ? "down"
            : "up";
      return (
        <WhipPan direction={direction} duration_f={durationInFrames}>
          {children}
        </WhipPan>
      );
    }
    case "static":
    case "keyframed":
    default:
      return <>{children}</>;
  }
};

/**
 * Stacks the shot-level effects that DO have a render primitive
 * (freeze/shake/rgb_split/flash - see PRIMITIVE_PARAM_CONTRACTS)  around
 * the slot's content. blur_pulse/overlay_grain/mask_cutout have no
 * corresponding entry in PRIMITIVE_PARAM_CONTRACTS at all (never did, in
 * either language) and are silently not rendered here - the Python bridge
 * (remotion_engine.py) is responsible for logging that gap into
 * RenderReport.approximations, not this component.
 *
 * Order (outer to inner): Freeze holds the frame, so it wraps everything;
 * Shake/RgbSplit are transforms on the frozen-or-live content; Flash
 * overlays last so its white flash sits visually on top of the rest.
 */
function wrapWithEffects(effects: ShotEffect[], children: React.ReactNode): React.ReactNode {
  let content = children;

  const shake = effects.find((e) => e.type === "shake");
  if (shake) {
    content = (
      <Shake amplitude_px={Number(shake.params.amplitude_px)} freq_hz={Number(shake.params.freq_hz)}>
        {content}
      </Shake>
    );
  }

  const rgbSplit = effects.find((e) => e.type === "rgb_split");
  if (rgbSplit) {
    content = (
      <RgbSplit
        offset_px_r={Number(rgbSplit.params.offset_px_r)}
        offset_px_b={Number(rgbSplit.params.offset_px_b)}
      >
        {content}
      </RgbSplit>
    );
  }

  const freeze = effects.find((e) => e.type === "freeze");
  if (freeze) {
    content = <Freeze duration_f={Number(freeze.params.duration_f)}>{content}</Freeze>;
  }

  const flash = effects.find((e) => e.type === "flash");
  if (flash) {
    content = (
      <Flash t={Number(flash.params.t)} duration_f={Number(flash.params.duration_f)}>
        {content}
      </Flash>
    );
  }

  return content;
}

/**
 * Renders a slot's bound video, honoring a speed_ramp effect if present by
 * splitting into per-segment Sequences with distinct playbackRate values
 * (playbackRate is constant per element - there's no way to animate it
 * continuously, matching signals/effects.py::detect_speed_ramp's own
 * piecewise-CONSTANT approximation, not a smooth curve).
 *
 * binding.asset_id is expected to be an http(s):// URL at this point, NOT
 * a raw filesystem path - see remotion_engine.py's staging-server comment
 * for why: OffthreadVideo's frame extraction goes through an HTTP proxy
 * that only accepts http(s):// sources (a raw absolute path gets
 * auto-converted to file:// and rejected outright), and headless
 * Chrome's own <video> element (the fallback considered during
 * debugging) refused local file:// media entirely regardless of
 * disable-web-security settings. The Python bridge stages every bound
 * asset through a short-lived local static file server and rewrites
 * asset_id to the resulting http://127.0.0.1:PORT/... URL before this
 * component ever sees it.
 *
 * Known limitation, documented rather than silently wrong: startFrom stays
 * fixed at binding.in_point_s for every segment rather than accounting for
 * elapsed source-time at different playback rates - correct compensation
 * would need cumulative source-time tracking this scaffold doesn't do yet.
 * Speed ramps are already an approximate signal end to end; this keeps
 * that approximation rather than adding false precision on top of it.
 */
function renderSlotVideo(slot: Slot, binding: AssetBinding, fps: number): React.ReactNode {
  const speedRampEffect = slot.applied.effects.find((e) => e.type === "speed_ramp");
  const startFrom = Math.round(binding.in_point_s * fps);

  if (speedRampEffect && Array.isArray(speedRampEffect.params.segments)) {
    const segments = speedRampEffect.params.segments as SpeedRampSegment[];
    if (segments.length > 0) {
      return (
        <SpeedRamp segments={segments} fps={fps}>
          {(rate) => <OffthreadVideo src={binding.asset_id} startFrom={startFrom} playbackRate={rate} />}
        </SpeedRamp>
      );
    }
  }

  return <OffthreadVideo src={binding.asset_id} startFrom={startFrom} />;
}

function textBoxStyle(box: TextLayer["box"], style: TextLayer["style"]): React.CSSProperties {
  return {
    position: "absolute",
    left: `${box.x * 100}%`,
    top: `${box.y * 100}%`,
    width: `${box.w * 100}%`,
    transform: box.anchor === "center" ? "translate(-50%, -50%)" : undefined,
    color: style.fill ?? "white",
    WebkitTextStroke: style.stroke ? `${style.stroke_px}px ${style.stroke}` : undefined,
    fontSize: `${style.size_rel * 100}vh`,
    textAlign: "center",
  };
}

/**
 * TextLayerAnimation only records WHICH animation category was detected
 * (in_/out/in_duration_f) - it has no reveal-RATE field (chars_per_f /
 * words_per_f), unlike the render primitives that need one. Rather than
 * add yet another cross-language schema field mid-build, the rate is
 * derived here at render time by spreading the string evenly across
 * in_duration_f - a reasonable rendering-time interpretation of an
 * approximate category, not a ground-truth signal that needs storing.
 *
 * caption_burnin/lyric roles conceptually want CaptionKaraoke's per-word
 * highlight, but Template carries no per-word transcript timing at all
 * (that lives on EditTrace.audio.transcript_words, which compile_template
 * never threads through to Template) - CaptionKaraoke is unused here
 * until that's wired up; these roles render through the same fallback as
 * any other layer instead of calling it with fabricated/empty data.
 *
 * slide_up/bounce have no dedicated render primitive at all (only pop/
 * typewriter/word_by_word/caption_karaoke exist in
 * PRIMITIVE_PARAM_CONTRACTS) - both fall back to a plain fade-in.
 */
function renderTextContent(layer: TextLayer): React.ReactNode {
  const text = layer.string;
  const inDuration = Math.max(1, layer.animation.in_duration_f);

  switch (layer.animation.in_) {
    case "pop":
      return <TextPop in_duration_f={inDuration}>{text}</TextPop>;
    case "typewriter":
      return <TextTypewriter chars_per_f={text.length / inDuration} text={text} />;
    case "word_by_word": {
      const wordCount = text.split(" ").length;
      return <TextWordByWord words_per_f={wordCount / inDuration} text={text} />;
    }
    case "fade":
    case "slide_up":
    case "bounce":
    default:
      return <span>{text}</span>;
  }
}

export const RecutEdit: React.FC<RecutEditProps> = ({template, bindings}) => {
  const {fps} = useVideoConfig();
  const slotRanges = computeSlotFrameRanges(template, fps);
  const bindingBySlot = new Map(bindings.bindings.map((b) => [b.slot_id, b]));

  return (
    <AbsoluteFill style={{backgroundColor: "black"}}>
      {slotRanges.map(({slot, fromFrame, durationInFrames}) => {
        const binding = bindingBySlot.get(slot.slot_id);
        const isUnresolved = !binding || bindings.unresolved_slots.includes(slot.slot_id);

        return (
          <Sequence key={slot.slot_id} from={fromFrame} durationInFrames={durationInFrames}>
            {isUnresolved || !binding ? (
              <MissingSlot slotId={slot.slot_id} />
            ) : (
              <MotionWrapper slot={slot} durationInFrames={durationInFrames}>
                {wrapWithEffects(slot.applied.effects, renderSlotVideo(slot, binding, fps))}
              </MotionWrapper>
            )}
          </Sequence>
        );
      })}

      {template.text_layers.map((layer) => {
        const fromFrame = Math.round(layer.t_in * fps);
        const durationInFrames = Math.max(1, Math.round((layer.t_out - layer.t_in) * fps));
        return (
          <Sequence key={layer.id} from={fromFrame} durationInFrames={durationInFrames}>
            <div style={textBoxStyle(layer.box, layer.style)}>{renderTextContent(layer)}</div>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
