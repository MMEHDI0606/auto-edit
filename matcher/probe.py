"""
L4 - per-asset feature extraction: duration/orientation/fps (delegates to
ingest/probe.py), face detection, shot-type classification, motion score,
CLIP embedding, optional Whisper if speech is present. See RECUT_SPEC.md
sec 6, step 2.

v1 approximations sanctioned by Unit 3.6 itself (not gaps to "fix" later
without a reason): Haar cascade face detection (a full DNN detector is out
of scope for a v1), a coarse face-bbox-size shot-type heuristic (not a real
shot-type classifier model), and a frame-diff energy motion score (not a
full estimate_affine_motion sweep across every frame pair in the asset -
that function is tuned for adjacent-frame pairs within one already-cut
shot, not for scanning an unbounded, un-shot-detected user asset).
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from ingest.probe import probe_media
from signals.audio import transcribe

_FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_CLOSEUP_FACE_AREA_FRACTION = 0.15  # face bbox area / frame area at/above this reads as "closeup"
_MOTION_SAMPLE_COUNT = 8  # evenly spaced frames sampled across the asset for the motion-score / CLIP frame
_SPEECH_CONFIDENCE_FLOOR = 0.5
# BUG FOUND during Unit 3.6 testing: faster-whisper, run against pure
# non-speech audio (this project's own click-track fixture), hallucinates
# an "..." token at HIGH confidence (>0.78) rather than returning nothing -
# confidence alone was not a reliable speech/non-speech signal. Fixed by
# also requiring at least one alphanumeric character in the word text
# (see _has_alphanumeric below) - filler/silence tokens like "..." carry
# no actual letters, real transcribed words always do.
_CLIP_MODEL_NAME = "ViT-B-32-quickgelu"  # NOT "ViT-B-32" - the openai pretrained weights use QuickGELU
                                          # activation; open_clip warns of an activation-function mismatch
                                          # (quick_gelu=False vs the checkpoint's quick_gelu=True) otherwise
_CLIP_PRETRAINED = "openai"


@dataclass
class AssetFeatures:
    asset_id: str
    # GAP FOUND during Unit 3.8 (matcher/assign.py): pick_in_point() needs
    # to reopen the asset's own video to slide a scoring window across it -
    # AssetFeatures originally carried every extracted feature EXCEPT a way
    # to find the file itself again.
    asset_path: str
    duration_s: float
    orientation: str
    has_face: bool
    shot_type_guess: str | None
    motion_score: float
    clip_embedding: list[float]
    has_speech: bool


_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None


def get_clip_model():
    """Lazily loads and caches the CLIP model/preprocess/tokenizer triple.
    Module-level singleton - loading CLIP weights is expensive; every
    extract_asset_features() call in this module, AND matcher/score.py's
    role-exemplar text embedding (Unit 3.7), share this one instance
    rather than each loading its own copy."""
    global _clip_model, _clip_preprocess, _clip_tokenizer
    if _clip_model is None:
        import open_clip

        _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
            _CLIP_MODEL_NAME, pretrained=_CLIP_PRETRAINED
        )
        _clip_model.eval()
        _clip_tokenizer = open_clip.get_tokenizer(_CLIP_MODEL_NAME)
    return _clip_model, _clip_preprocess, _clip_tokenizer


def _orientation(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "vertical" if height > width else "horizontal"


def _sample_frames(cap: cv2.VideoCapture, count: int) -> list[np.ndarray]:
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        return []
    indices = sorted({round(i * (total - 1) / max(1, count - 1)) for i in range(count)})
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    return frames


def _detect_face(frame: np.ndarray) -> tuple[bool, float]:
    """Returns (has_face, largest_face_bbox_area / frame_area)."""
    cascade = cv2.CascadeClassifier(_FACE_CASCADE_PATH)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(faces) == 0:
        return False, 0.0
    frame_area = frame.shape[0] * frame.shape[1]
    _, _, w, h = max(faces, key=lambda f: f[2] * f[3])
    return True, (w * h) / frame_area


def frame_diff_motion_score(frames: list[np.ndarray]) -> float:
    """Frame-diff energy across the sampled frames: mean absolute
    grayscale pixel difference between consecutive samples, normalized to
    roughly [0, 1] - the v1 approximation Unit 3.6 itself sanctions in
    place of a full affine-motion sweep."""
    if len(frames) < 2:
        return 0.0
    diffs = []
    for a, b in zip(frames, frames[1:]):
        gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
        gray_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
        diffs.append(float(np.mean(np.abs(gray_a - gray_b))) / 255.0)
    return float(np.mean(diffs))


def _clip_embedding(frame_bgr: np.ndarray) -> list[float]:
    model, preprocess, _tokenizer = get_clip_model()
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    tensor = preprocess(Image.fromarray(rgb)).unsqueeze(0)
    with torch.no_grad():
        features = model.encode_image(tensor)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.squeeze(0).tolist()


def _has_alphanumeric(word: str) -> bool:
    return any(c.isalnum() for c in word)


def _extract_wav(asset_path: Path, wav_path: Path) -> None:
    # Same mono/22050Hz convention as ingest/normalize.py's wav extraction -
    # matches librosa/faster-whisper's expected input, avoids a silent
    # resample happening redundantly downstream.
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(asset_path), "-ar", "22050", "-ac", "1", str(wav_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def extract_asset_features(asset_path: Path, asset_id: str) -> AssetFeatures:
    probe = probe_media(asset_path)

    cap = cv2.VideoCapture(str(asset_path))
    if not cap.isOpened():
        raise ValueError(f"could not open {asset_path}")
    try:
        frames = _sample_frames(cap, _MOTION_SAMPLE_COUNT)
    finally:
        cap.release()
    if not frames:
        raise ValueError(f"{asset_path} has no readable frames")

    representative_frame = frames[len(frames) // 2]
    has_face, face_area_fraction = _detect_face(representative_frame)
    shot_type_guess = "closeup" if (has_face and face_area_fraction >= _CLOSEUP_FACE_AREA_FRACTION) else "wide"

    has_speech = False
    if probe.has_audio:
        with tempfile.TemporaryDirectory() as tmp_dir:
            wav_path = Path(tmp_dir) / "asset.wav"
            _extract_wav(asset_path, wav_path)
            words = transcribe(wav_path)
            has_speech = any(
                w["conf"] >= _SPEECH_CONFIDENCE_FLOOR and _has_alphanumeric(w["word"]) for w in words
            )

    return AssetFeatures(
        asset_id=asset_id,
        asset_path=str(asset_path),
        duration_s=probe.duration_s,
        orientation=_orientation(probe.width, probe.height),
        has_face=has_face,
        shot_type_guess=shot_type_guess,
        motion_score=frame_diff_motion_score(frames),
        clip_embedding=_clip_embedding(representative_frame),
        has_speech=has_speech,
    )
