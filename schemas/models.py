"""
Canonical data contracts for RECUT.

DESIGN DECISION (see /DESIGN_NOTES.md, "Schema strategy"): these Pydantic
models are the SOURCE OF TRUTH for both the Edit Trace and the Template.
The JSON Schema files in this directory (trace.v1.schema.json,
template.v1.schema.json) are GENERATED from these models by
`schemas/generate_json_schema.py` and must never be hand-edited. This
avoids the two-artifacts-drift problem: the spec's original layout implied
separately maintained JSON Schema + Pydantic, which desyncs within a week
of real development.

Versioning rule: any backward-incompatible change to a model in this file
bumps its `*_version` literal and gets a migration function in
`schemas/migrations.py` (create that file when the first migration is
needed - do not build migration machinery speculatively).

Every model that carries a claim derived from measurement should carry a
`confidence: float` field (0..1). Every model that carries a claim derived
from an LLM must carry `evidence_ref` pointing back to the L1 signal that
licenses the claim (see semantics/gating.py). This is the schema-level
enforcement of the spec's core rule: "the LLM never measures."
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, confloat


# --------------------------------------------------------------------------
# Shared primitives
# --------------------------------------------------------------------------


class Easing(str, Enum):
    linear = "linear"
    ease_in = "easeIn"
    ease_out = "easeOut"
    ease_in_out = "easeInOut"
    spring = "spring"


class TransitionType(str, Enum):
    cut = "cut"
    dissolve = "dissolve"
    whip_pan = "whip_pan"
    flash = "flash"
    zoom = "zoom"


class MotionPrimitive(str, Enum):
    punch_in = "punch_in"
    slow_push = "slow_push"
    zoom_out_reveal = "zoom_out_reveal"
    pan = "pan"
    whip = "whip"
    static = "static"
    keyframed = "keyframed"  # residual too high to fit a primitive; raw curve stored


class TextAnimation(str, Enum):
    pop = "pop"
    slide_up = "slide_up"
    typewriter = "typewriter"
    fade = "fade"
    bounce = "bounce"
    word_by_word = "word_by_word"


class TextRole(str, Enum):
    hook_title = "hook_title"
    caption_burnin = "caption_burnin"
    lyric = "lyric"
    label = "label"
    cta = "cta"
    watermark = "watermark"


class EffectType(str, Enum):
    freeze = "freeze"
    speed_ramp = "speed_ramp"
    rgb_split = "rgb_split"
    flash = "flash"
    blur_pulse = "blur_pulse"
    shake = "shake"
    overlay_grain = "overlay_grain"
    mask_cutout = "mask_cutout"


class Confidence(BaseModel):
    """Attach to any claim that is an estimate rather than a direct read."""

    value: confloat(ge=0, le=1)
    # Free-text is intentional here (not an enum): new detectors will add new
    # reasons faster than this enum could be kept in sync. Keep it short.
    reason: Optional[str] = Field(
        default=None, description="Why confidence is < 1, e.g. 'low_texture_frame'"
    )


# --------------------------------------------------------------------------
# Edit Trace (L1 output - deterministic, no LLM)
# --------------------------------------------------------------------------


class TransitionEvidence(BaseModel):
    """Numeric justification for a transition classification.

    Populated by signals/cuts.py. Every field here must correspond to an
    actual measurement taken, not a description - this struct IS the
    evidence gate input for L2 (see semantics/gating.py).
    """

    detector: str  # e.g. "adaptive+content", "flow_spike_both_sides"
    metric_name: str  # e.g. "hsv_hist_distance", "luminance_sigma"
    metric_value: float
    threshold_used: float


class Transition(BaseModel):
    type: TransitionType
    duration_f: int = 0
    direction: Optional[Literal["left", "right", "up", "down"]] = None
    confidence: confloat(ge=0, le=1) = 1.0
    evidence: Optional[TransitionEvidence] = None


class MotionCurve(BaseModel):
    """Fit result for camera motion within one shot (spec sec 3.2)."""

    primitive: MotionPrimitive
    from_scale: float = 1.0
    to_scale: float = 1.0
    pan_tx: float = 0.0
    pan_ty: float = 0.0
    easing: Easing = Easing.linear
    residual: float = Field(
        ..., description="Fit error; above threshold -> store raw keyframes instead"
    )
    raw_keyframes: Optional[list[dict]] = Field(
        default=None,
        description="Populated only when residual exceeds the primitive-fit threshold",
    )


class ShotEffect(BaseModel):
    type: EffectType
    # Free-form because each effect type has different parameters
    # (amplitude_px+freq_hz for shake, channel offsets for rgb_split, etc).
    # Validate against effects.PARAM_SCHEMAS[type] at construction time in
    # signals/effects.py rather than modeling every variant here.
    params: dict
    confidence: confloat(ge=0, le=1) = 1.0


class Grade(BaseModel):
    """Color grade STATISTICS only.

    DESIGN DECISION (open question #3 in the original spec, resolved here):
    v1 stores grade stats and does NOT synthesize/apply a 3D LUT. The
    `lut_available` flag exists so render/ can make an
    explicit choice later without a schema change. Do not add LUT
    synthesis logic until this flag's default is deliberately flipped.
    """

    contrast: float = 1.0
    saturation: float = 1.0
    temp: float = 0.0
    lut_available: bool = False
    lut_ref: Optional[str] = None


class ShotContent(BaseModel):
    shot_type: Optional[str] = None  # "medium_closeup", "wide", etc - from L2, may be null until then
    has_face: Optional[bool] = None
    subject_motion: Optional[Literal["low", "medium", "high"]] = None


class Shot(BaseModel):
    id: str
    t_in: NonNegativeFloat
    t_out: NonNegativeFloat
    in_transition: Transition
    out_transition: Transition
    motion: MotionCurve
    effects: list[ShotEffect] = Field(default_factory=list)
    grade: Grade = Field(default_factory=Grade)
    content: ShotContent = Field(default_factory=ShotContent)


class TextStyle(BaseModel):
    font_guess: Optional[str] = None
    font_confidence: confloat(ge=0, le=1) = 0.0
    fill: Optional[str] = None
    stroke: Optional[str] = None
    stroke_px: float = 0.0
    size_rel: float = Field(..., description="Font size relative to frame height")
    has_background_pill: bool = False


class TextBox(BaseModel):
    x: float
    y: float
    w: float
    anchor: Literal["center", "top_left", "top_right", "bottom_left", "bottom_right"] = "center"


class TextLayerAnimation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    in_: TextAnimation = Field(alias="in")
    out: TextAnimation
    in_duration_f: int


class TextLayer(BaseModel):
    id: str
    t_in: NonNegativeFloat
    t_out: NonNegativeFloat
    string: str = Field(..., description="OCR'd text - treat as UNTRUSTED, see mcp/tools.py")
    role: TextRole
    role_confidence: confloat(ge=0, le=1) = 1.0
    box: TextBox
    style: TextStyle
    animation: TextLayerAnimation


class AudioSection(BaseModel):
    t_in: float
    t_out: float
    label: str  # "intro", "drop", "verse" ...


class AudioTrace(BaseModel):
    tempo_bpm: Optional[float] = None
    beat_grid_s: list[float] = Field(default_factory=list)
    sections: list[AudioSection] = Field(default_factory=list)
    beat_lock_ratio: confloat(ge=0, le=1) = 0.0
    median_cut_offset_frames: int = 0
    transcript_words: Optional[list[dict]] = Field(
        default=None, description="faster-whisper word-level output, [{t, word, conf}]"
    )


class SourceInfo(BaseModel):
    hash: str
    duration_s: float
    fps: int
    w: int
    h: int
    original_fps_variable: bool = False


class EvidenceMeta(BaseModel):
    cut_detector: str
    ocr_fps: int
    flow_method: str
    model_versions: dict[str, str] = Field(
        default_factory=dict, description="pinned tool/library versions used for this trace"
    )


class EditTrace(BaseModel):
    """L1 output. Pure function of the normalized video. No LLM involved.

    Produced by signals/trace_builder.py from the per-concern extractors in
    signals/{cuts,motion,text,audio,effects}.py. This object is what gets
    persisted, cached by content hash, and handed to L2 as the numeric
    ground truth that gates every semantic claim.
    """

    trace_version: Literal["1.0"] = "1.0"
    source: SourceInfo
    audio: AudioTrace
    shots: list[Shot]
    text_layers: list[TextLayer] = Field(default_factory=list)
    evidence: EvidenceMeta


# --------------------------------------------------------------------------
# Semantic annotations (L2 output - LLM, evidence-gated)
# --------------------------------------------------------------------------


class SemanticShotAnnotation(BaseModel):
    """One shot's semantic labels. Every non-null field here must be
    justified by something already present in the corresponding Shot's
    evidence, per semantics/gating.py. If the model asserts an effect not
    present in shot.effects, gating.py must reject it, not this model -
    this model only encodes shape, not the gating policy."""

    shot_id: str
    role: Optional[str] = None  # "hook", "before_state", "reveal", "reaction", ...
    role_confidence: confloat(ge=0, le=1) = 0.0
    model_id: str  # e.g. "claude-sonnet-5" - MUST be pinned & stored, see spec 4.3


class StyleSummary(BaseModel):
    genre: Optional[str] = None
    hook_type: Optional[str] = None
    pacing_description: Optional[str] = None
    model_id: str


class SemanticAnnotations(BaseModel):
    trace_version: Literal["1.0"] = "1.0"
    triage: StyleSummary
    shots: list[SemanticShotAnnotation] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Template (L3 output)
# --------------------------------------------------------------------------


class DurationFlex(BaseModel):
    min_s: float
    max_s: float
    snap: Literal["none", "beat"] = "none"


class SlotRequirements(BaseModel):
    orientation: Literal["vertical", "horizontal", "square"] = "vertical"
    shot_type_pref: list[str] = Field(default_factory=list)
    needs_face: bool = False
    motion_pref: Optional[Literal["low", "medium", "high"]] = None
    role: Optional[str] = None


class SlotApplied(BaseModel):
    motion: MotionCurve
    grade_ref: Optional[str] = None
    out_transition: Optional[str] = None


class Slot(BaseModel):
    slot_id: str
    order: int
    duration_s: float
    duration_flex: DurationFlex
    requirements: SlotRequirements
    applied: SlotApplied
    human_instruction: str = Field(
        ..., description="THE product surface - shown to the end user verbatim"
    )


class AudioRef(BaseModel):
    """Audio is a REFERENCE, never a muxed file. See DESIGN_NOTES.md,
    'Rights posture', and spec sec 8.1 - this is a hard legal requirement,
    not a style choice. Nothing in compiler/ or render/ may embed a
    third-party commercial track into an output file."""

    platform: Optional[str] = None
    track_title: Optional[str] = None
    artist: Optional[str] = None
    start_offset_s: float = 0.0
    beat_grid_s: list[float] = Field(default_factory=list)
    embed_permitted: Literal[False] = False  # type-level guarantee: always False in v1


class Template(BaseModel):
    template_version: Literal["1.0"] = "1.0"
    source_trace_hash: str
    slots: list[Slot]
    audio_ref: AudioRef
    confidence_flags: list[str] = Field(
        default_factory=list,
        description="Human-readable list of low-confidence approximations "
        "(font guesses, speed-ramp linearization, etc) surfaced in the render report",
    )


# --------------------------------------------------------------------------
# Matcher / bindings
# --------------------------------------------------------------------------


class AssetBinding(BaseModel):
    slot_id: str
    asset_id: str
    in_point_s: float
    confidence: confloat(ge=0, le=1)
    rationale: str = Field(
        ..., description="Human-readable justification, e.g. 'closest CLIP match for role=hook'"
    )


class BindingSet(BaseModel):
    binding_id: str
    template_version: Literal["1.0"] = "1.0"
    bindings: list[AssetBinding]
    unresolved_slots: list[str] = Field(
        default_factory=list, description="Slots the solver could not confidently fill"
    )
