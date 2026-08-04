import {CalculateMetadataFunction, Composition} from "remotion";
import {RecutEdit} from "./RecutEdit";
import type {RecutEditProps} from "./recutTypes";
import {computeTotalDurationInFrames} from "./timeline";

// Fixed per Settings.render_width/render_height/normalize_fps (common/config.py)
// - opts.resolution can still override width/height per render, but fps is
// not currently an opts field (see RenderOptions in render/interface.py).
const FPS = 30;

const calculateMetadata: CalculateMetadataFunction<RecutEditProps> = ({props}) => {
  const [width, height] = props.opts.resolution;
  return {
    durationInFrames: computeTotalDurationInFrames(props.template, FPS),
    fps: FPS,
    width,
    height,
  };
};

const EMPTY_PROPS: RecutEditProps = {
  template: {
    template_version: "1.0",
    source_trace_hash: "",
    slots: [],
    audio_ref: {
      platform: null,
      track_title: null,
      artist: null,
      start_offset_s: 0,
      beat_grid_s: [],
      embed_permitted: false,
    },
    text_layers: [],
    confidence_flags: [],
  },
  bindings: {binding_id: "", template_version: "1.0", bindings: [], unresolved_slots: []},
  opts: {include_audio: false, resolution: [1080, 1920]},
};

export const RecutComposition = () => {
  return (
    <Composition
      id="RecutEdit"
      component={RecutEdit}
      durationInFrames={30}
      fps={FPS}
      width={1080}
      height={1920}
      defaultProps={EMPTY_PROPS}
      calculateMetadata={calculateMetadata}
    />
  );
};
