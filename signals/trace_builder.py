"""
L1 orchestrator - assembles cuts.py + motion.py + text.py + audio.py +
effects.py output into one validated EditTrace (schemas.models.EditTrace).

This is the ONLY function in signals/ that should be called from outside
the package (ingest -> trace_builder -> semantics). Individual extractor
modules are intentionally kept independently unit-testable; this module
owns the ordering constraints between them, specifically:

  1. mask_watermark_regions() must run first and its output frames must be
     what motion.py / text.py operate on (spec sec 8.3).
  2. audio.transcribe() and audio.separate_speech_music() must complete
     before text.classify_role() can be called (role classification needs
     the transcript to distinguish captions from lyrics).
  3. cuts.detect_cuts() must complete before audio.compute_beat_lock()
     (needs cut_times_s).

Failure policy: if any sub-extractor throws, trace_builder does not
silently drop that piece of the trace - it either propagates the error
(preferred, "fail loudly") or, if the extractor supports partial output,
records a confidence-zero placeholder and continues. In practice (Unit
1.17): every call below propagates exceptions EXCEPT the effects.py
detectors, whose own documented contract is "return None on absence" -
that None is not an error, it just means Shot.effects gets nothing
appended for that detector.

INTEGRATION NOTE not obvious from any single unit's own tests: cuts.py,
motion.py, and text.py's OCR path all take a VIDEO FILE PATH, not an
in-memory frame array - but the watermark-masked frames (constraint #1)
only exist in memory after mask_watermark_regions() runs. Rather than
retrofit those already-tested modules to accept frame arrays, this module
writes the masked frames out to a temp video once and points every
path-based extractor at THAT file instead of the original normalized
video. This was not visible until integration - each unit's own tests
passed against the real (unmasked, since none had a watermark) fixture
clip.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import librosa
import numpy as np

from common.config import load_settings
from ingest.cache import hash_file
from schemas.models import (
    AudioSection,
    AudioTrace,
    EditTrace,
    EvidenceMeta,
    Shot,
    ShotContent,
    SourceInfo,
    TextBox,
    TextLayer,
    TextLayerAnimation,
    Transition,
    TransitionType,
)
from signals import audio as audio_mod
from signals import cuts as cuts_mod
from signals import effects as effects_mod
from signals import motion as motion_mod
from signals import text as text_mod

_MUSIC_ACTIVE_RMS_FLOOR = 0.01  # no_vocals-stem RMS above this counts as "music playing" in a text-layer window
_AUDIO_ACTIVE_RMS_FLOOR = 0.005  # whole-mix RMS above this counts as "audio continues" for detect_freeze


def _parse_frame_rate(rate_str: str) -> float:
    if "/" in rate_str:
        num, den = rate_str.split("/", 1)
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    return float(rate_str)


def _read_all_frames(video_path: Path) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def _write_video(frames: list[np.ndarray], out_path: Path, *, fps: float, width: int, height: int) -> Path:
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return out_path


def _rms_in_window(y: np.ndarray, sr: int, t_in: float, t_out: float) -> float:
    start, end = max(0, int(t_in * sr)), min(len(y), int(t_out * sr))
    if end <= start:
        return 0.0
    return float(np.sqrt(np.mean(y[start:end] ** 2)))


def _shot_motion_magnitude_series(shot_frames: list[np.ndarray], fallback_threshold: int) -> list[float]:
    """Recomputes per-frame-pair motion magnitude for detect_speed_ramp().
    ShotMotionResult (motion.extract_shot_motion) only returns the FITTED
    curve, not the raw per-pair series speed-ramp detection needs - this
    duplicates a small part of that function's internal loop rather than
    widening its return type again."""
    magnitudes = []
    for a, b in zip(shot_frames[:-1], shot_frames[1:]):
        M, inliers = motion_mod.estimate_affine_motion(a, b)
        if M is not None and inliers >= fallback_threshold:
            tx, ty = float(M[0, 2]), float(M[1, 2])
        else:
            tx, ty, _scale = motion_mod.dense_flow_fallback(a, b)
        magnitudes.append(float(np.hypot(tx, ty)))
    return magnitudes


def build_trace(normalized_video_path: Path, wav_path: Path, probe: dict) -> EditTrace:
    """Runs the full L1 pipeline and returns a validated EditTrace.
    Raises pydantic.ValidationError if any sub-extractor produces output
    that doesn't satisfy the schema - this should never happen in
    production and indicates a bug in the extractor, not bad input data.
    """
    settings = load_settings()

    video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    fps = round(_parse_frame_rate(video_stream.get("avg_frame_rate") or video_stream["r_frame_rate"]))
    width, height = int(video_stream["width"]), int(video_stream["height"])
    duration_s = float(probe["format"].get("duration") or video_stream.get("duration") or 0.0)
    source_hash = hash_file(normalized_video_path)

    # --- ordering constraint #1: mask BEFORE motion/text see frames ---
    all_frames = _read_all_frames(normalized_video_path)
    masked_frames, masked_rects = effects_mod.mask_watermark_regions(all_frames)

    with tempfile.TemporaryDirectory() as tmp_dir:
        masked_video_path = _write_video(
            masked_frames, Path(tmp_dir) / "masked.mp4", fps=fps, width=width, height=height
        )

        # --- cuts (boundary times + classified transitions, same boundaries) ---
        boundary_times = cuts_mod.detect_boundaries(
            masked_video_path, min_scene_len_frames=settings.scene_detect_min_scene_len_frames
        )
        transitions = cuts_mod.detect_cuts(
            masked_video_path, min_scene_len_frames=settings.scene_detect_min_scene_len_frames
        )

        # --- audio (constraint #2 lives inside: transcribe/separate before role classification below) ---
        tempo_bpm, beat_grid_s = audio_mod.extract_beat_grid(wav_path)
        sections = audio_mod.extract_sections(wav_path)
        transcript_words = audio_mod.transcribe(wav_path)
        vocals_path, no_vocals_path = audio_mod.separate_speech_music(wav_path)
        # constraint #3: beat-lock needs cut_times_s, which needs cuts to have already run
        beat_lock_ratio, median_cut_offset_frames = audio_mod.compute_beat_lock(boundary_times, beat_grid_s, fps=fps)

        y_full, sr = librosa.load(str(wav_path), sr=None)
        no_vocals_y, no_vocals_sr = librosa.load(str(no_vocals_path), sr=None)

        # --- shots ---
        boundary_and_transition = list(zip(boundary_times, transitions))
        shot_bounds = [0.0, *boundary_times, duration_s]
        start_cut = Transition(type=TransitionType.cut, confidence=1.0)
        end_cut = Transition(type=TransitionType.cut, confidence=1.0)
        in_transitions = [start_cut] + [t for _time, t in boundary_and_transition]
        out_transitions = [t for _time, t in boundary_and_transition] + [end_cut]

        shots: list[Shot] = []
        for i, (t_in, t_out) in enumerate(zip(shot_bounds[:-1], shot_bounds[1:])):
            start_frame, end_frame = int(round(t_in * fps)), int(round(t_out * fps))
            shot_frames = masked_frames[start_frame:end_frame]
            if len(shot_frames) < 2:
                shot_frames = masked_frames[start_frame : start_frame + 2] or masked_frames[-2:]

            motion_result = motion_mod.extract_shot_motion(masked_video_path, t_in, t_out)

            shot_effects = []
            audio_active = _rms_in_window(y_full, sr, t_in, t_out) > _AUDIO_ACTIVE_RMS_FLOOR
            freeze = effects_mod.detect_freeze(shot_frames, audio_active=audio_active)
            if freeze is not None:
                shot_effects.append(freeze)

            if len(shot_frames) >= 6:
                magnitude_series = _shot_motion_magnitude_series(
                    shot_frames, settings.flow_inlier_fallback_threshold
                )
                try:
                    pitch_series, _voiced, _prob = librosa.pyin(
                        y_full[int(t_in * sr) : int(t_out * sr)],
                        fmin=librosa.note_to_hz("C2"),
                        fmax=librosa.note_to_hz("C7"),
                        sr=sr,
                    )
                    pitch_series = [float(p) for p in pitch_series if not np.isnan(p)]
                except Exception:
                    pitch_series = []
                speed_ramp = effects_mod.detect_speed_ramp(magnitude_series, pitch_series)
                if speed_ramp is not None:
                    shot_effects.append(speed_ramp)

            rgb_split = effects_mod.detect_rgb_split(shot_frames)
            if rgb_split is not None:
                shot_effects.append(rgb_split)

            luminance_series = [
                (t_in + j / fps, float(np.mean(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))))
                for j, f in enumerate(shot_frames)
            ]
            flash = effects_mod.detect_flash(luminance_series, beat_grid_s)
            if flash is not None:
                shot_effects.append(flash)

            blur_pulse = effects_mod.detect_blur_pulse(shot_frames, fps=fps)
            if blur_pulse is not None:
                shot_effects.append(blur_pulse)

            shake_amplitude = motion_result.shake_amplitude_px
            if shake_amplitude > 0.5:
                from schemas.models import EffectType, ShotEffect

                shot_effects.append(
                    ShotEffect(
                        type=EffectType.shake,
                        params={"amplitude_px": shake_amplitude, "freq_hz": motion_result.shake_freq_hz},
                        confidence=1.0,
                    )
                )

            grade = effects_mod.grade_stats(shot_frames)

            shots.append(
                Shot(
                    id=f"s{i + 1}",
                    t_in=t_in,
                    t_out=t_out,
                    in_transition=in_transitions[i],
                    out_transition=out_transitions[i],
                    motion=motion_result.curve,
                    effects=shot_effects,
                    grade=grade,
                    content=ShotContent(),  # L2 territory - stays null in Phase 1, per schema docstring
                )
            )

        # --- text layers ---
        raw_boxes = text_mod.sample_and_ocr(masked_video_path, sample_fps=settings.ocr_sample_fps)
        grouped_layers = text_mod.group_into_layers(raw_boxes)

        median_size_rel = float(np.median([l["box"][3] for l in grouped_layers])) if grouped_layers else 0.0

        text_layers: list[TextLayer] = []
        for i, layer in enumerate(grouped_layers):
            midpoint_t = (layer["t_in"] + layer["t_out"]) / 2
            midpoint_frame_idx = min(len(masked_frames) - 1, max(0, int(round(midpoint_t * fps))))
            style = text_mod.extract_text_style(masked_frames[midpoint_frame_idx], layer["box"])

            # Reconstruct this layer's own per-frame track from raw_boxes by
            # position (IoU) match - group_into_layers only retains the
            # latest box, not a full history; alpha has no dedicated
            # estimator anywhere yet (Unit 1.8's own docstring flags it as
            # caller-supplied), so it's left at a constant 1.0 (unknown).
            track = [
                {"box": b["box"], "alpha": 1.0}
                for b in raw_boxes
                if layer["t_in"] <= b["t"] <= layer["t_out"]
                and text_mod.bbox_iou(b["box"], layer["box"]) >= 0.3
            ]
            in_animation, out_animation, in_duration_f = text_mod.classify_entrance_exit(track or [{"box": layer["box"], "alpha": 1.0}])

            music_active = _rms_in_window(no_vocals_y, no_vocals_sr, layer["t_in"], layer["t_out"]) > _MUSIC_ACTIVE_RMS_FLOOR
            role, role_confidence = text_mod.classify_role(
                layer,
                transcript_words=transcript_words,
                music_active=music_active,
                video_duration_s=duration_s,
                median_size_rel=median_size_rel,
            )

            box_x, box_y, box_w, _box_h = layer["box"]
            text_layers.append(
                TextLayer(
                    id=f"t{i + 1}",
                    t_in=layer["t_in"],
                    t_out=layer["t_out"],
                    string=layer["string"],
                    role=role,
                    role_confidence=role_confidence,
                    box=TextBox(x=box_x, y=box_y, w=box_w),
                    style=style,
                    animation=TextLayerAnimation(**{"in": in_animation, "out": out_animation, "in_duration_f": in_duration_f}),
                )
            )

        audio_trace = AudioTrace(
            tempo_bpm=tempo_bpm,
            beat_grid_s=beat_grid_s,
            sections=[AudioSection(**s) for s in sections],
            beat_lock_ratio=beat_lock_ratio,
            median_cut_offset_frames=median_cut_offset_frames,
            transcript_words=transcript_words,
        )

        evidence = EvidenceMeta(
            cut_detector="adaptive+content",
            ocr_fps=settings.ocr_sample_fps,
            flow_method=settings.flow_method_primary,
            model_versions={"watermark_masked_rects": str(len(masked_rects))},
        )

        return EditTrace(
            source=SourceInfo(
                hash=source_hash, duration_s=duration_s, fps=fps, w=width, h=height, original_fps_variable=False
            ),
            audio=audio_trace,
            shots=shots,
            text_layers=text_layers,
            evidence=evidence,
        )
