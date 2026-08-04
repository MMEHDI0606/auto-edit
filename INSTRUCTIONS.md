# RECUT — Build Instructions (execution-level, one unit at a time)

This document is the execution companion to `BUILD_ORDER.md` (which gives
phase-level gates) and `DESIGN_NOTES.md` (which gives the "why"). This file
gives you, unit by unit, the exact scope, algorithm, done-criteria, and
dependency for every piece of functionality in the scaffold, in the order
to build them.

**Rule: finish a unit completely — implemented, tested, passing its done
criteria — before starting the next one.** Do not leave a unit half-built
to go start another. Do not build two units in parallel. If a unit's done
criteria can't be met, stop and fix that unit; don't move on and hope it
gets fixed later.

Each unit specifies:
1. **Scope** — exactly what's in, what's explicitly deferred.
2. **Implementation** — which stub file(s), and the algorithm/library
   calls/parameters to use. Where I give a concrete threshold or formula,
   use it as the starting value — these are the judgment calls already
   made; don't re-derive them, tune them empirically against the eval
   harness once it exists (Unit 1.19 onward).
3. **Done criteria** — what to check before moving on.
4. **Dependencies** — what must already exist.

Library API signatures below reflect the APIs as of this scaffold's
writing. If a pinned version's actual signature differs slightly, adapt
the call but **do not change the algorithm, threshold, or ordering logic**
without noting the deviation in `DESIGN_NOTES.md`.

---

## PHASE 0 — Contracts & scaffolding sanity

### Unit 0.1 — Dependency pinning
**Scope.** Pin exact versions in `pyproject.toml` for every dependency
currently unpinned. In scope: `yt-dlp`, `opencv-python`, `scenedetect`,
`librosa`, `faster-whisper`, `pydantic`, `fastapi`, `celery`, `redis`. Out
of scope: anything only needed by Phase 2+ (Remotion/Node deps, CLIP,
Demucs, PaddleOCR) — pin those in the phase that first uses them, not now
(a dependency pinned but unused for months just goes stale).
**Implementation.** For `yt-dlp` specifically: pin to a specific release
tag (not a floating range) and record that exact version string as a
constant importable from `ingest/downloader.py::pin_yt_dlp_version()` —
this is not cosmetic, it's what lets a future regression be bisected to a
yt-dlp upgrade (spec §8.2).
**Done criteria.** `pip install -e ".[dev]"` succeeds in a clean venv with
no unpinned-dependency warnings; `python -c "import cv2, scenedetect,
librosa, faster_whisper, pydantic, fastapi"` succeeds.
**Dependencies.** None — first unit.

### Unit 0.2 — Schema completeness pass
**Scope.** Walk `schemas/models.py` field-by-field against
`RECUT_SPEC.md` §3.6 (Edit Trace) and §5.1/§5.2 (Template/slot/audio_ref).
Confirm every field mentioned in the spec's abridged JSON examples has a
corresponding typed field in the Pydantic models (most already do — this
is a verification pass, not a rewrite). Add anything missing.
**Implementation.** No new files. Edit `schemas/models.py` only if a gap
is found. After any edit, regenerate: `python schemas/generate_json_schema.py`
from inside `schemas/`.
**Done criteria.** `pytest tests/test_schemas.py -q` passes; the two
generated `.schema.json` files are re-committed if changed;
`git diff --stat schemas/models.py` (or equivalent) is reviewed by a human
before moving on — a schema change at this stage is cheap, a schema change
after Phase 1 code depends on the old shape is not.
**Dependencies.** Unit 0.1 (need pydantic installed to run the generator).

### Unit 0.3 — Golden set annotation format
**Scope.** Finalize the annotation JSON shape for one golden-set video
(the format description already in `eval/golden/.gitkeep`), and hand-pick
the first 3 real short-form videos (any genre) to annotate first — this
is preparation, not full annotation of all 20-30 yet (that happens
incrementally through Phase 1, see Unit 1.19).
**Implementation.** Create `eval/golden/<video_id>/annotations.json` for
those 3 videos with, at minimum: `cuts: [{t, type}]`,
`text_layers: [{t_in, t_out, string, box}]`, `beat_grid_s: [...]`. Hand-
label by scrubbing the video frame-by-frame (e.g. in a video editor or
`ffmpeg`-extracted frame sequence) — there is no shortcut here, this is
manual ground truth.
**Done criteria.** 3 videos have a `source.ref` (URL or note on how to
obtain the file — do not commit the video itself) and a hand-verified
`annotations.json` that a second look-through confirms matches the video.
**Dependencies.** None (can run in parallel with 0.1/0.2, but must be done
before Unit 1.19's gate check).

Note: if a donor supplies an editor project file (`.fcpxml`/Premiere XML/
`.otio`) alongside their video, use Unit 0.4's importer to draft this
video's `annotations.json` instead of frame-by-frame scrubbing — Unit 0.4
still ends with the same human "second look-through" done-criterion above,
it just removes the scrubbing labor to get there.

### Unit 0.4 — Project-file ground-truth importer (OTIO-based)
**Scope.** Implement `eval/golden/import_project_file.py`, a golden-set
*acquisition* tool, not a pipeline component — it never runs in
production, only ahead of `eval/run.py` / as an alternative on-ramp into
Unit 0.3's annotation format. Given an editor project file (`.fcpxml` from
Final Cut Pro X, the `.xml` Final Cut Pro 7 interchange format Premiere
Pro exports via File > Export > Final Cut Pro XML, or native `.otio`)
plus its matching source video, produce a draft
`eval/golden/<video_id>/annotations.json` with hand-scrubbing-free cut
timestamps and cut/transition types, and — best-effort only, not a done
criterion — text/graphic-layer timing if the project has a dedicated
overlay track. Explicitly out of scope: CapCut project files (proprietary,
undocumented, no OTIO adapter exists — do not attempt) and After Effects
`.aep` (proprietary binary container; text timing is frequently
expression-driven rather than keyframed, so even a successful parse often
can't recover "exact" text timing — do not attempt). See
`DESIGN_NOTES.md` §16 for the full rationale. This unit does NOT replace
video acquisition — the donor must still supply the actual video
(`source.ref`); a project file only replaces the *scrubbing* labor, not
the *footage* requirement.
**Implementation.**
- Dependency: add `opentimelineio` (and `opentimelineio-contrib` for the
  modern-FCPXML and AAF adapters, which are NOT in OTIO core) to a new
  `golden-import` extra in `pyproject.toml` — eval-tooling only, same
  posture as the `ocr`/`audio-sep` extras, not a production dependency.
  Pin exact versions per Unit 0.1's policy; confirm the latest released
  version against PyPI at implementation time.
- Format detection: sniff the file's root XML element, don't trust the
  extension (editors name these files inconsistently). `<fcpxml ...>` =
  Apple's modern Final Cut Pro X format → OTIO's `fcpx_xml` adapter
  (contrib, less consistently maintained against Apple's newest DTD
  versions — treat as best-effort). `<xmeml ...>` = the legacy Final Cut
  Pro 7 XML interchange (this is what Premiere Pro actually exports as
  "Final Cut Pro XML") → OTIO core's `fcp_xml` adapter (mature, in-tree,
  the most reliable of the three paths). `.otio` = native → OTIO core's
  `otio_json` adapter, direct and lossless. Pass `adapter_name` explicitly
  to `otio.adapters.read_from_file()` based on this sniff — do not rely on
  OTIO's extension-based auto-dispatch, since `.xml` alone is ambiguous.
  AAF (`.aaf`, an alternative Premiere export) is supported best-effort
  only via contrib's AAF adapter (needs `pyaaf2`); not required to work
  for this unit's done criteria.
- Track selection: real project files have multiple video tracks (a base
  edit track plus graphics/title tracks above it). Pick the lowest-indexed
  video track with near-continuous coverage of the timeline duration as
  the **cut/shot track**; treat any higher tracks as **candidate overlay
  tracks** for text-layer extraction only.
- Flatten: walk the cut track's children in order (`track.each_child()`),
  skipping `Gap` items (log a warning instead of bridging silently —
  RECUT's `Shot` list assumes continuous coverage, and a real gap needs a
  human decision) and reading `Transition` items positioned between two
  `Clip`s. Compute each `Clip`'s timeline-space `t_in`/`t_out` from
  `clip.transformed_time_range(track)` converted to seconds — NOT
  `source_range`, which is the *source media's* in/out, not the timeline
  position.
- Transition-type mapping. OTIO's `Transition.transition_type` is generic
  (SMPTE-style constants plus adapter-specific strings), not RECUT's
  5-value enum — map explicitly, falling back conservatively:
  - No `Transition` object between clips (hard edit) → `cut`,
    confidence `exact`.
  - `transition_type == "SMPTE_Dissolve"` (or the adapter-preserved raw
    name contains "dissolve"/"fade") → `dissolve`, confidence `exact`.
  - Raw effect/transition name (check `transition.metadata` first — the
    `fcp_xml`/`fcpx_xml` adapters often keep the source element's
    `name`/`effect` string under a namespaced metadata key; only fall back
    to a second raw-XML pass over the same file if metadata is empty)
    contains "whip" → `whip_pan`; contains "flash"/"flare"/"strobe" →
    `flash`; contains "zoom"/"cross zoom"/"push" → `zoom` — all at
    confidence `heuristic`.
  - Any other named `Transition` (wipe, page peel, unrecognized vendor
    plugin name) → `cut`, confidence `fallback_cut` — emit it, don't drop
    it, but flag it plainly.
  Every emitted cut entry carries two fields beyond Unit 0.3's
  `{t, type}`: `source: "project_file"` and
  `type_confidence: "exact"|"heuristic"|"fallback_cut"`, so
  `eval/metrics.py` and human reviewers can tell a project-file-derived
  label from a hand-scrubbed one, and treat `fallback_cut` entries as
  needing a manual spot-check before trusting them for
  `transition_type_accuracy()`.
- Text-layer extraction (best-effort, not a done-criterion): only attempt
  it where an overlay-track clip's `name` looks like literal on-screen
  text (common for FCPX title clips and Premiere graphic clips named
  after their content); emit as `text_layers` entries with
  `source: "project_file_heuristic"` — box/font/style are NOT recoverable
  this way and stay null.
- Markers: if present, surface as a separate `candidate_beat_grid_s` list
  — never write directly into `beat_grid_s` (a marker could mean chapter
  mark, note-to-self, anything); only a human confirming against the
  audio should promote a candidate into the real beat grid.
- Do not commit the project file itself to git — same posture as the
  video (see `eval/golden/.gitkeep`): project files routinely embed
  absolute local file paths and the donor's OS username (a privacy leak,
  not a copyright one, but still don't ship it). Store
  `eval/golden/<video_id>/project_file.ref` (a note on how to re-obtain
  it) and commit only the derived, sanitized `annotations.json`.
**Done criteria.** Run against at least 2 real project files (any mix of
`.fcpxml`/legacy-XML/`.otio`) donated alongside their source videos:
produces a draft `annotations.json` whose `cuts[]` timestamps match the
video to within 1 frame on manual spot-check, and every transition entry
emitted with `type_confidence: exact` is actually correct (`heuristic`/
`fallback_cut` entries are expected to need human correction — that's the
point of the confidence flag, not a failure of this unit).
**Dependencies.** Unit 0.3 (the annotation format this writes into).
Independent of Phase 1's analysis code — can run against externally
donated files as soon as any donor offers a project file, in parallel
with the LinkedIn ask going out.

---

## PHASE 1 — Analysis (L0 + L1), CLI only, no LLM, no renderer

### Unit 1.1 — Ingest: normalize + probe
**Scope.** Implement `ingest/normalize.py::normalize()` and `probe()`, and
`ingest/probe.py::probe_media()`. In scope: file upload path only. Out of
scope: `ingest/downloader.py` (yt-dlp) — build that in Unit 1.1b, after
this works, so a URL-download bug never blocks the analysis pipeline from
being provable on uploaded files.
**Implementation.**
- `probe()` / `probe_media()`: shell out to `ffprobe -v quiet -print_format
  json -show_format -show_streams <path>`, parse JSON. Extract duration,
  `r_frame_rate` (compare to `avg_frame_rate` — if they differ, the source
  is VFR), width/height, rotation (from stream tags or side_data), audio
  stream presence.
- `normalize()`: run exactly the command in `RECUT_SPEC.md` §2.2:
  ```
  ffmpeg -i in.mp4 -vsync cfr -r {fps} -pix_fmt yuv420p \
         -vf "scale={width}:{height}:force_original_aspect_ratio=decrease" \
         -c:v libx264 -crf {crf} -c:a pcm_s16le norm.mp4
  ```
  using `common.config.Settings` for `fps`/`width`/`height`/`crf` (do not
  hardcode). Also extract WAV: `ffmpeg -i norm.mp4 -ar 22050 -ac 1
  norm.wav` (mono, 22050Hz is librosa's typical default — matches
  `librosa.load`'s default `sr`).
  Build `original_to_normalized_time_map`: if source was CFR already, this
  is the identity map (list of `(t, t)` at some sparse interval, e.g. every
  1s, is enough — you don't need per-frame granularity). If VFR, use
  `ffprobe -show_entries packet=pts_time` on the original to get per-frame
  original timestamps, and pair them against the frame index in the
  normalized (now-CFR) output by frame order.
- Raise `subprocess.CalledProcessError` unmodified on ffmpeg/ffprobe
  failure — do not catch and wrap it into a generic exception (fail
  loudly, per project-wide policy stated in the docstring).
**Done criteria.** Given 3-5 real short-form MP4s (mix of CFR phone
capture and re-encoded/downloaded files), `normalize()` produces a
constant-fps output verified by re-`probe`-ing the output and confirming
`r_frame_rate == avg_frame_rate`. Write a unit test in
`tests/signals/` — actually put it in a new `tests/ingest/` dir — that
runs this against at least 1 real fixture file checked into
`eval/golden/` or a small `tests/fixtures/` dir (a few-second clip is
fine, doesn't need to be a full golden video).
**Dependencies.** Unit 0.1 (ffmpeg/ffprobe must be on PATH — verify with
`ffmpeg -version` — these are system binaries, not pip packages; document
the required install in a comment if not already present in the repo).

### Unit 1.1b — Ingest: yt-dlp downloader
**Scope.** Implement `ingest/downloader.py::fetch()`. Only single-URL,
on-demand fetch — no bulk/scheduled crawling (see `DESIGN_NOTES.md`, this
boundary is load-bearing, not just tidy).
**Implementation.** Use the `yt-dlp` Python API (`import yt_dlp;
yt_dlp.YoutubeDL(opts).download([url])`) rather than shelling out, so
exceptions are catchable Python exceptions. Wrap any `yt_dlp.utils.
DownloadError` (or extractor-not-found error) into `UnsupportedSourceError`
— callers must only ever see this one exception type. Bounded retry: 2
attempts, 2s backoff between them, then raise. `opts` should force best
video+audio muxed to mp4 (`format: "bestvideo+bestaudio/best"`,
`merge_output_format: "mp4"`).
**Done criteria.** Fetching one known-stable public YouTube Short
succeeds and the result feeds directly into Unit 1.1's `normalize()`
without modification. Fetching a deliberately-broken/unsupported URL
raises `UnsupportedSourceError`, not a raw yt-dlp exception — write a test
asserting this.
**Dependencies.** Unit 1.1 (downloader output must be normalize-able).

### Unit 1.2 — Ingest: content-hash cache
**Scope.** Implement `ingest/cache.py::hash_file()`, `get()`, `put()`.
Defer `purge()` implementation to Phase 5 (Unit 5.2) — the *function
signature and call sites* should exist now so nothing has to be
retrofitted, but the actual deletion logic (and its admin-facing trigger)
isn't needed until real user/rights-holder data exists.
**Implementation.** `hash_file()`: SHA256 over the **normalized** video
bytes (read in chunks, e.g. 1MB, to avoid loading a full video into
memory: `hashlib.sha256()` + `.update()` in a loop). `get()`/`put()`: for
Phase 1, a filesystem-backed cache is sufficient — store under
`{Settings.cache_root}/{hash}/` with `norm.mp4`, `norm.wav`, `probe.json`,
and later `trace.json`. Don't build the Postgres-backed version (spec
§10's stated storage choice) until Phase 4/5 when there's an API layer to
back — a filesystem cache is the right scope for a CLI-only Phase 1.
**Done criteria.** Running `cli/analyze.py` (Unit 1.18) twice on the same
source file produces a cache hit the second time (verify via a log line
or a returned `from_cache: true` flag) and does not re-invoke ffmpeg.
**Dependencies.** Unit 1.1 (needs a normalized file to hash).

### Unit 1.3 — Watermark masking (must precede motion/text)
**Scope.** Implement `signals/effects.py::mask_watermark_regions()`.
Static-corner-region masking only — this is a preprocessing step, not a
full watermark detector. In scope: TikTok/IG-style logo bugs that sit in a
fixed screen position for the entire video. Out of scope: moving or
per-platform-specific watermark recognition.
**Implementation.** Compute a per-pixel temporal variance map over a
sample of frames (e.g. every 10th frame across the whole video,
`np.var(stacked_frames, axis=0)`). Regions with near-zero variance AND
non-background luminance (i.e., not just static black bars) in a corner
quadrant (define corners as the outer 15% width/height in each of the 4
corners) are candidate watermark regions. Mask candidates by
alpha-blending them to the surrounding local median color (inpainting via
`cv2.inpaint` with a small radius is acceptable, or simpler: replace with
`cv2.medianBlur` patch) before frames are handed to `motion.py`/`text.py`.
Return the list of masked rectangles so `trace_builder.py` can log them
into `EvidenceMeta`.
**Done criteria.** On a video with a visible corner watermark (most
TikTok reposts have one), the masked-frame output visibly removes it
(spot check a few frames) and does not touch dynamic content that happens
to sit in a corner (e.g. a scene where the subject moves through a
corner — variance there should NOT be near-zero, so it should not be
masked; test this with a hand-picked positive+negative example, not just
one clip).
**Dependencies.** Unit 1.1 (needs normalized frames).

### Unit 1.4 — Shot boundary detection
**Scope.** Implement `signals/cuts.py::reconcile_detectors()` first
(pure function, easiest to unit test), then the boundary-detection half
of `detect_cuts()` (boundary times only — transition *type* classification
is Unit 1.5, kept separate on purpose so this unit's test doesn't depend
on that logic existing yet).
**Implementation.**
- Run PySceneDetect twice: once with `ContentDetector(threshold=27.0,
  min_scene_len=Settings.scene_detect_min_scene_len_frames)`, once with
  `AdaptiveDetector(adaptive_threshold=3.0,
  min_scene_len=Settings.scene_detect_min_scene_len_frames)`. Use the
  library's `SceneManager` + `detect()` API against the **normalized,
  watermark-masked** video (Unit 1.3's output), not the raw upload.
  `min_scene_len` MUST read from `Settings.scene_detect_min_scene_len_frames`
  (default 3) — never the library default (spec §3.1's central warning).
- `reconcile_detectors(adaptive_boundaries, content_boundaries, fps)`:
  union both boundary-time lists, then merge any two boundaries within 1
  frame (`1/fps` seconds) of each other into a single boundary (keep the
  earlier timestamp). Return the merged, sorted list.
**Done criteria.** Unit test in `tests/signals/test_cuts.py` using
`eval/fixtures.py`-style synthetic boundary lists (e.g.
`adaptive=[1.0, 1.03, 5.0]`, `content=[1.01, 5.0, 8.2]` at fps=30 →
expect merged `[1.0, 5.0, 8.2]`) — no real video needed for this test.
Separately, run the real detector against 3-5 real clips and manually
verify (by scrubbing) that rapid cuts (6-10 frame shots) are NOT merged
into longer shots — this is the specific failure mode `min_scene_len`
tuning exists to prevent.
**Dependencies.** Unit 1.3 (operates on masked frames).

### Unit 1.5 — Transition classification
**Scope.** Implement the classification half of `detect_cuts()`: given
boundary timestamps from Unit 1.4, classify each into
`TransitionType` (cut / dissolve / whip_pan / flash / zoom).
**Implementation.** Check in this exact priority order, first match wins
(this ordering is deliberate, see the docstring in `signals/cuts.py` — a
whip pan can also produce a brief luminance spike, so flash must be
checked as a *global full-frame* condition and whip as a *directional
flow* condition to avoid misclassifying one as the other):
1. **flash**: mean luminance (grayscale frame mean) at the boundary frame
   exceeds the shot's baseline mean by > 2σ (σ computed over the shot's
   own frames, not the whole video). If true → `flash`, done.
2. **whip_pan**: compute dense optical flow magnitude (Farneback) on the
   3 frames before and 3 frames after the boundary; if the mean magnitude
   on BOTH sides exceeds a threshold (start at 15 px/frame at 1080x1920,
   tune empirically) AND the pre/post average flow direction is
   consistent (dot product of average flow vectors > 0, i.e. same general
   direction) → `whip_pan`, with `direction` from the sign/angle of the
   average flow vector (bucket into left/right/up/down by dominant axis).
   If the flow spike is present on only ONE side, do NOT classify as
   whip_pan — fall through to cut (spec §8.3's explicit mitigation for
   "whip read as a cut" applies in reverse here too: don't over-call whip
   from a one-sided spike).
3. **zoom**: affine scale factor (from Unit 1.6's per-frame affine
   estimate, computed for the frames spanning the boundary) shows a
   discontinuity — i.e., the scale trend within the shot before the
   boundary differs by more than a threshold (start at 5% scale jump in a
   single frame pair) from the trend after. This check has a soft
   dependency on Unit 1.6's affine estimator being available as a
   function — call `signals.motion.estimate_affine_motion` directly for
   just the boundary-adjacent frame pairs, not the full per-shot curve fit.
4. **dissolve**: HSV histogram distance between consecutive frames stays
   elevated (above a baseline threshold) for a sustained 3-15 frame window
   around the boundary, AND the distance-over-time curve in that window is
   monotonic (rises then the two shots' content blends) rather than a
   single spike.
5. **cut** (default): single-frame HSV histogram distance
   (`cv2.compareHist` with `cv2.HISTCMP_BHATTACHARYYA` or chi-square) spike
   exceeding a threshold at exactly the boundary frame, no sustained
   elevation. This is also the fallback when nothing above matched.
Populate `TransitionEvidence` (detector name, metric_name, metric_value,
threshold_used) for every classification — this is required, not optional,
it's what Unit 3.1's evidence gate checks against later.
**Done criteria.** Against the 3 golden videos annotated in Unit 0.3 (plus
1-2 with a whip pan and 1-2 with a dissolve, hand-picked if the first 3
don't have one), transition-type accuracy (Unit 1.19's metric) is
computed and reviewed — no fixed bar yet at this stage, just confirm the
classifier assigns *something other than "cut" for every non-cut* on
those hand-picked examples before moving on (a classifier that labels
everything "cut" would technically hit high cut-boundary F1 while being
useless — check for this specific degenerate case).
**Dependencies.** Unit 1.4 (boundary timestamps), Unit 1.6's
`estimate_affine_motion` function signature (not its full curve-fit
output — just call the frame-pair primitive).

### Unit 1.6 — Camera motion estimation
**Scope.** Implement `signals/motion.py` in full:
`estimate_affine_motion()`, `dense_flow_fallback()`, `fit_motion_curve()`,
`compute_shake_score()`, `extract_shot_motion()`.
**Implementation.**
- `estimate_affine_motion(frame_a, frame_b)`: `orb = cv2.ORB_create(
  nfeatures=2000)`; detect+compute keypoints/descriptors on both frames;
  match with `cv2.BFMatcher(cv2.NORM_HAMMING)` + `knnMatch(des_a, des_b,
  k=2)`; apply Lowe's ratio test (keep matches where
  `m.distance < 0.75 * n.distance`); if fewer than 10 good matches, return
  `(None, 0)` immediately (let the caller fall back). Otherwise call
  `cv2.estimateAffinePartial2D(pts_a, pts_b, method=cv2.RANSAC,
  ransacReprojThreshold=3.0)`, return `(M, inlier_count)` where
  `inlier_count = inliers.sum()`.
- Fallback trigger: in `extract_shot_motion()`, if
  `inlier_count < Settings.flow_inlier_fallback_threshold` (default 20),
  call `dense_flow_fallback()` instead for that frame pair and record
  which method was used per-frame-pair (this becomes part of
  `EvidenceMeta.model_versions`, e.g. `{"flow_method_shot_s3": "farneback"}`).
- `dense_flow_fallback()`: `cv2.calcOpticalFlowFarneback(prev_gray,
  next_gray, None, pyr_scale=0.5, levels=3, winsize=15, iterations=3,
  poly_n=5, poly_sigma=1.2, flags=0)`. Derive an approximate
  (tx, ty, scale) from the flow field: `tx, ty` = median flow vector;
  `scale` ≈ 1 + (mean radial flow component / frame diagonal) — radial
  component computed relative to frame center.
- Decompose `M` (from the affine path) into: `tx = M[0,2]`, `ty = M[1,2]`,
  `scale = sqrt(M[0,0]**2 + M[1,0]**2)`, `rotation =
  atan2(M[1,0], M[0,0])`.
- `fit_motion_curve()`: accumulate per-frame-pair `(tx, ty, scale)` into
  cumulative series across the shot. Fit against each `MotionPrimitive` by
  least-squares against the primitive's parametric form combined with each
  `Easing` function (linear, easeIn = t², easeOut = 1-(1-t)², easeInOut =
  standard cubic smoothstep, spring = damped-oscillation approximation —
  implement these 5 easing functions once as a shared small utility, don't
  reimplement per primitive). Try `static` (near-zero everywhere),
  `punch_in`/`slow_push`/`zoom_out_reveal` (scale ramps), `pan`/`whip`
  (tx/ty ramps) — compute residual (sum of squared error, normalized by
  series length) for each candidate and pick the lowest. If the best
  residual exceeds a threshold (start at 0.05 normalized), set
  `primitive="keyframed"` and store the raw `(t, tx, ty, scale)` samples in
  `raw_keyframes` instead of forcing a bad primitive fit.
- `compute_shake_score()`: detrend `(tx, ty)` (subtract the fitted
  primitive's predicted curve, or a low-order polynomial fit if primitive
  is `keyframed`), then compute high-frequency energy via FFT — sum of
  power spectral density above ~4Hz (assuming `fps`≈30, high-frequency
  handheld shake is typically 5-15Hz). Report both `amplitude_px` (RMS of
  the detrended residual) and `freq_hz` (dominant frequency in the
  high-pass band) as a `ShotEffect(type=EffectType.shake)` — NOT a
  `MotionCurve` field, it coexists with an underlying primitive per the
  docstring.
**Done criteria.** Unit test with a synthetic frame-pair sequence
(construct via `np.roll`/`cv2.warpAffine` on a single textured test image
to create a KNOWN affine transform — e.g. apply a known 1.1x scale ramp
across 10 synthetic frames) confirms `fit_motion_curve` recovers
`punch_in` with `to_scale≈1.1` within a small tolerance. Separately, run
against 2-3 real shots with visible zoom/pan (from the golden set) and
manually confirm the classified primitive matches what you see.
**Dependencies.** Unit 1.3 (masked frames). Unit 1.5 needs this module's
`estimate_affine_motion` function to exist (signature only) before Unit
1.5's zoom-transition check can be finished — build the function
signature and the affine half of this unit before finishing Unit 1.5, or
build 1.5's zoom-check last within its own unit after confirming 1.6 is
available. Recommended order: finish 1.6 fully, THEN do 1.5's zoom check
(swap the two units' final integration order if that's cleaner — the
important constraint is that 1.5 cannot be *fully* done, including its
zoom branch, until 1.6 exists).

> **Correction to strict sequencing above:** because Unit 1.5 (transition
> classification, zoom branch) depends on Unit 1.6 (`estimate_affine_motion`),
> actually build them in this order: 1.4 → 1.6 → 1.5. Treat the ordering
> in this document as 1.4, 1.6, 1.5, 1.7, 1.8, ... going forward — the
> numbering stays for reference but 1.6 must physically be implemented
> before 1.5's zoom branch.

### Unit 1.7 — On-screen text: OCR + temporal grouping
**Scope.** Implement `signals/text.py::sample_and_ocr()` and
`group_into_layers()`. Out of scope for this unit: style extraction,
animation classification, role classification, font matching (Units 1.9,
1.10).
**Implementation.**
- `sample_and_ocr()`: sample frames at `Settings.ocr_sample_fps` (default
  8, not 1 — text can flash <500ms). Use PaddleOCR:
  `ocr = PaddleOCR(use_angle_cls=True, lang='en')`,
  `result = ocr.ocr(frame, cls=True)` per sampled frame, extract
  `[{t, text, box: [x,y,w,h] normalized to frame w/h, conf}]`. Normalize
  boxes to `[0,1]` range relative to 1080×1920 (or whatever the actual
  normalized resolution is) so downstream comparisons are
  resolution-independent.
- `group_into_layers()`: greedy temporal clustering — walk sampled frames
  in time order; for each detected box, compare against currently "open"
  layers using `iou_threshold` (default 0.5) on normalized bbox AND
  `string_sim_threshold` (default 0.8, use
  `difflib.SequenceMatcher(None, a, b).ratio()` or Levenshtein ratio) on
  text. If a box matches an open layer on both criteria, extend that
  layer's `t_out` to the current frame's time. If it matches on IoU but
  NOT string similarity, treat it as closing the old layer and opening a
  new one at the same position (this is the "two distinct strings in the
  same box must not merge" case flagged in the docstring). If a box
  matches neither, open a new layer. Close any layer not matched in the
  current sampled frame with a small grace window (e.g. skip 1 missed
  frame before closing, to tolerate a single OCR miss) — tune this grace
  window empirically.
**Done criteria.** Unit test in `tests/signals/test_text.py` for
`group_into_layers()` using a synthetic box sequence (no real OCR) that
includes: (a) one string persisting across frames → one layer; (b) two
different strings in the same screen position back-to-back → two
separate layers; (c) a single missed frame in the middle of a persisting
string → still one layer (grace window). Separately, run
`sample_and_ocr` + `group_into_layers` on 2-3 real golden videos with
visible on-screen text and manually check t_in/t_out against the video.
**Dependencies.** Unit 1.3 (masked frames — critical, since unmasked
platform watermarks pollute OCR per spec §8.3).

### Unit 1.8 — Text style + animation classification
**Scope.** Implement the remaining pieces of `signals/text.py`:
`classify_entrance_exit()` and the style-extraction portion of
`extract_text_layers()` (position/size, fill/stroke color, background
pill). Explicitly DEFER `font_match()` to its own follow-up unit (1.8b) —
font matching is approximate-by-design and doesn't gate the Phase 1
success metric (text timing IoU + CER), so don't let it block finishing
this unit.
**Implementation.**
- Style: for each layer, take the frame at its temporal midpoint. Crop to
  the bbox. Fill color: sample the mode (most common) color within the
  glyph mask (threshold the crop to isolate high-contrast glyph pixels via
  Otsu's method, `cv2.threshold(..., cv2.THRESH_OTSU)`). Stroke color/width:
  sample the ring of pixels immediately outside the glyph mask (dilate the
  mask by a few px, subtract the original mask, sample that ring).
  Background pill: check if a rectangular region behind the text has a
  distinct, roughly-uniform color different from the general shot
  background (compare the bbox's expanded background region's color
  variance to the surrounding frame's variance).
- Animation: track the bbox size and mean-alpha (approximate alpha via
  edge density or via `cv2.absdiff` against the background estimate) over
  the first/last 8 sampled frames of the layer. Classify:
  - `pop`: bbox scale increases rapidly (>20% growth) within first 2-3
    frames then stabilizes.
  - `slide_up`: bbox y-position decreases monotonically over the first
    frames while x/size stay ~constant.
  - `typewriter`: string length visible (via incremental OCR matches, if
    resolvable) grows over the entrance frames — if this signal isn't
    reliably recoverable from OCR sampling alone at 8fps, it's acceptable
    to leave this classification lower-confidence/best-effort — record
    confidence accordingly, don't force a guess.
  - `fade`: alpha increases monotonically with bbox otherwise static.
  - `bounce`: y-position oscillates (over/undershoots) before settling.
  - `word_by_word`: bbox width grows in discrete word-sized steps rather
    than continuously (best-effort, same caveat as typewriter).
  Default to `fade` when no clear signal (safest/most common animation) and
  record low confidence rather than guessing a specific animation you
  can't justify.
**Done criteria.** Manual review against 5-10 real text layers across 2-3
golden videos: for each, does the classified entrance/exit animation match
what you see when scrubbing? Track a rough tally (doesn't need to hit a
percentage bar yet — that's Unit 1.19's job) and confirm the classifier
isn't defaulting to one label for everything.
**Dependencies.** Unit 1.7 (layers must exist to extract style/animation
from).

### Unit 1.8b — Font matching (deferred, best-effort)
**Scope.** Implement `signals/text.py::font_match()`. Explicitly optional
for the Phase 1 gate — build this only after Unit 1.19's core gate is
passing, or skip it in Phase 1 entirely and revisit in Phase 2/3 if time
allows. Flagging it as its own unit so it's never accidentally treated as
blocking.
**Implementation.** Curate a small font library (10-20 common
short-form-video fonts: Montserrat, Poppins, TikTok Sans equivalents,
Proxima Nova, etc — whatever's actually reasonable to license/bundle).
For a glyph crop, render each candidate font at matching size/weight,
compute a raster similarity score (normalized cross-correlation or simple
pixel-diff after aligning on centroid), return the top-3 by score with
their similarity as `font_confidence`. Always keep top-3 available for
user override even though the schema only stores the top pick —note this
in a comment for when the UI/MCP layer wants to expose alternatives.
**Done criteria.** Given 5 known font crops (hand-picked from real
videos, note down what font you believe it actually is from visual
inspection), the top-3 list includes something visually plausible for at
least 3/5 — this is inherently approximate, don't chase higher.
**Dependencies.** Unit 1.8.

### Unit 1.9 — Audio: beat grid, tempo, sections
**Scope.** Implement `signals/audio.py::extract_beat_grid()` and
`extract_sections()`. Out of scope: transcript (1.10), stem separation
(1.11), beat-lock (1.12).
**Implementation.**
- `extract_beat_grid()`: `y, sr = librosa.load(wav_path, sr=22050)`;
  `tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)`;
  `beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()`.
  Return `(float(tempo), beat_times)`.
- `extract_sections()`: compute a chromagram or MFCC feature matrix
  (`librosa.feature.mfcc`), run agglomerative/spectral clustering across
  time-windowed features (`sklearn.cluster.AgglomerativeClustering` or
  librosa's own `librosa.segment.agglomerative`) to get boundary frames,
  convert to `t_in`/`t_out` pairs. Label sections generically (`section_1`,
  `section_2`, ...) rather than guessing "intro"/"drop" semantically at
  this layer — semantic section labeling is exactly the kind of claim
  that belongs in L2 (with evidence gating), not L1. Store the L1 labels
  as generic positional identifiers; L2 can relabel with semantic names
  later if evidence supports it.
**Done criteria.** On 3 golden videos with known/countable tempo (tap
along by hand or use a reference BPM if the track is identifiable),
`extract_beat_grid`'s tempo is within ~5 BPM of the hand-counted value
(tempo octave errors — detecting half or double tempo — are a known
librosa failure mode; if it happens, it's fine to note and address later,
don't block on solving it perfectly in Phase 1).
**Dependencies.** Unit 1.1 (WAV extraction).

### Unit 1.10 — Audio: transcript
**Scope.** Implement `signals/audio.py::transcribe()`.
**Implementation.** `from faster_whisper import WhisperModel; model =
WhisperModel("base", device="cpu", compute_type="int8")` (CPU-friendly
default; document that a GPU box can use `device="cuda"` +
`compute_type="float16"`). `segments, info = model.transcribe(wav_path,
word_timestamps=True)`. Flatten to `[{t: word.start, word: word.word,
conf: word.probability}, ...]` from each segment's `.words`.
**Done criteria.** On 2-3 golden videos with clear speech, spot-check the
transcript against what's actually said — word-level timestamps should be
within ~200ms of the actual spoken word (loose tolerance is fine, this
feeds role classification, not a hard metric in Unit 1.19's gate).
**Dependencies.** Unit 1.1 (WAV).

### Unit 1.11 — Audio: speech/music separation + text role classification
**Scope.** Implement `signals/audio.py::separate_speech_music()` and
`signals/text.py::classify_role()`. These are grouped into one unit
because role classification is the actual consumer of the
speech/music split — building the split alone with no consumer to
validate it against isn't useful.
**Implementation.**
- `separate_speech_music()`: shell out to Demucs:
  `demucs --two-stems=vocals -o {out_dir} {wav_path}`, which produces
  `{out_dir}/htdemucs/{name}/vocals.wav` and `.../no_vocals.wav`. Return
  those two paths. This is a real, somewhat slow step (seconds to
  low-minutes per video on CPU) — note the cost in a comment; it's why
  spec §8.5 flags this as a latency contributor.
- `classify_role()`: for each text layer, compute a "music_active" signal
  as RMS energy of the `no_vocals` stem during `[t_in, t_out]` relative to
  its baseline; compute a "speech_active" signal similarly from the
  `vocals` stem AND check whether `transcript_words` has words whose time
  range overlaps `[t_in, t_out]` with reasonable string similarity to the
  OCR'd layer text. Decision order:
  1. If layer position/style matches known watermark patterns (bottom
     corner, low contrast, persists near-constantly) → `watermark`.
  2. If OCR string closely matches overlapping transcript words (string
     similarity > 0.6, generous because OCR errors compound with ASR
     errors) AND speech_active is high → `caption_burnin`.
  3. If music_active is high and speech_active is low/absent for that
     window → `lyric`.
  4. If the layer appears in roughly the first 20% of the video duration
     and has large/prominent styling (size_rel above median for the
     video) → `hook_title`.
  5. If the layer's string is short (<=3 words) and appears near the very
     end of the video → `cta` (best-effort heuristic; low confidence is
     fine here).
  6. Default → `label`.
  Record `role_confidence` reflecting how many of the above signals agreed
  vs. required a default fallback.
**Done criteria.** On 3-5 golden-video text layers spanning at least 2 of
the 6 roles, manual review confirms role assignment matches obvious
ground truth (an on-screen lyric during a song with no speech should not
be classified `caption_burnin`, etc). This is the concrete test for the
spec §8.3 "burned-in captions vs speech" failure mode — deliberately
construct or find a test case with both a caption AND a lyric in the same
video if possible.
**Dependencies.** Unit 1.9 (not directly, but conceptually parallel),
Unit 1.10 (transcript), Unit 1.8 (text layers must exist).

### Unit 1.12 — Cut-to-beat alignment
**Scope.** Implement `signals/audio.py::compute_beat_lock()`.
**Implementation.** For each cut time in `cut_times_s`, find the nearest
beat in `beat_grid_s` (binary search or linear scan — video-length lists
are small, don't over-engineer). Compute the signed offset in frames:
`offset_f = round((cut_time - nearest_beat_time) * fps)`. **Do not take
absolute value and do not clip to zero** — the sign matters (spec: editors
cut 1-3 frames *before* the beat). `beat_lock_ratio` = fraction of cuts
whose absolute offset is within some tolerance (e.g. ±3 frames) of a beat.
`median_cut_offset_frames` = median of the signed offsets across all cuts
that DO lock to a beat (exclude cuts with no nearby beat from the median
calculation, but count them as non-locked in the ratio).
**Done criteria.** Unit test with a synthetic beat grid
(`[0.0, 0.5, 1.0, 1.5]`) and cut times deliberately offset by a known
amount (e.g. `[0.48, 0.97]` at fps=30 → expect offset ≈ -1 frame each,
median ≈ -1, NOT 0). This test is specifically guarding the "don't snap to
zero" regression called out repeatedly in the docstrings — make sure it
would fail loudly if someone "simplified" the function to always report 0.
**Dependencies.** Unit 1.4 (cut times), Unit 1.9 (beat grid).

### Unit 1.13 — Effects: freeze, flash, blur_pulse (simple detectors)
**Scope.** Implement `signals/effects.py::detect_freeze()`,
`detect_flash()`, `detect_blur_pulse()`. These three are grouped because
they're all simple threshold-on-a-scalar-series detectors, structurally
identical in shape.
**Implementation.**
- `detect_freeze()`: for consecutive frames within a shot, compute
  `cv2.absdiff` mean; if it stays near-zero (below a small threshold, e.g.
  <1.0 on a 0-255 scale) for >= some frame count (e.g. 6+ frames, ~0.2s at
  30fps) WHILE the corresponding audio RMS energy in that window is NOT
  near-zero (i.e., audio continues), flag `freeze` with `duration_f` =
  length of the near-zero run.
- `detect_flash()`: per-frame mean luminance; flag `flash` at any local
  maximum exceeding baseline (shot's own mean) by > 2σ AND that timestamp
  is within a small tolerance of a beat position (`beat_grid_s`) — this
  ties flash detection to the beat grid per spec §3.5's effects table.
  Note: this is a distinct, shot-INTERNAL flash detector from Unit 1.5's
  transition-boundary flash check — that one classifies a *cut type*,
  this one flags a *mid-shot effect*. Keep them separate; don't merge the
  logic even though the luminance-spike math is similar.
- `detect_blur_pulse()`: compute Laplacian variance per frame
  (`cv2.Laplacian(gray, cv2.CV_64F).var()`) across the shot; flag a dip
  (variance drops below some fraction, e.g. 40%, of the shot's median
  Laplacian variance) as `blur_pulse` with `t_in`/`t_out` = the dip's
  extent.
Each detector returns `None` when below threshold — do not return a
low-confidence positive for a borderline case; that's the evidence-gating
principle discussed in the module docstring (a detector that "sort of
always fires weakly" breaks L2's evidence gate later).
**Done criteria.** Hand-construct or find one real example of each effect
in the golden set (a freeze-frame moment, a beat-synced flash, a blur
transition) and confirm the detector fires on it and does NOT fire on 2-3
shots without that effect (spot check for false positives, not just true
positives).
**Dependencies.** Unit 1.4 (shot boundaries, to segment frames per shot),
Unit 1.9 (beat grid, for flash).

### Unit 1.14 — Effects: speed ramp (approximate)
**Scope.** Implement `signals/effects.py::detect_speed_ramp()`. Explicitly
approximate per spec §8.3 ("information is genuinely destroyed... 2-3
linear segments... flag low confidence") — do not attempt full curve
recovery.
**Implementation.** Using the per-frame-pair motion magnitude series
already computed in Unit 1.6 (`sqrt(tx^2+ty^2)` or optical flow magnitude
if that was the fallback path) plus an audio pitch-tracking series
(`librosa.pyin` for fundamental frequency, or a simpler proxy: tempo
estimated over a sliding window within the shot), look for a
discontinuity: motion magnitude changes rate abruptly mid-shot AND audio
pitch/tempo shifts correspondingly (a true speed ramp changes both video
motion apparent speed and audio pitch together, since it's a played-back
speed change). Fit the motion-magnitude-over-time curve within the shot to
2-3 piecewise-linear segments (simple: try 1 breakpoint first via a grid
search over candidate breakpoint frames minimizing total segment fit
error; only try 2 breakpoints if 1 doesn't fit well). Store the segments
as `{t_in, t_out, rate}` in `ShotEffect.params["segments"]`, and always
set a confidence noticeably below 1.0 (e.g. 0.5-0.6) to signal the
approximation to L2/render.
**Done criteria.** On 1-2 golden-video examples with an obvious speed
ramp (visually sped-up or slowed-down mid-shot), the detector fires with a
`segments` list that roughly matches (by eye) where the ramp starts/ends.
Precision here is inherently loose — the done bar is "fires on the obvious
cases, doesn't fire on constant-speed shots," not a numeric accuracy
target.
**Dependencies.** Unit 1.6 (motion magnitude series), Unit 1.9/1.10
(audio pitch/tempo signal).

### Unit 1.15 — Effects: RGB split / glitch
**Scope.** Implement `signals/effects.py::detect_rgb_split()`.
**Implementation.** Split each frame into R/G/B channels. Compute
cross-correlation between R and G, and between B and G (using
`cv2.matchTemplate` with `cv2.TM_CCORR_NORMED` on small patches, or
`np.correlate`/FFT-based cross-correlation on flattened channel
differences) to find the pixel offset that maximizes correlation between
channels. If the best-fit offset is > 0 (channels are spatially
misaligned relative to each other) beyond a noise floor (e.g. > 1px),
flag `rgb_split` with `offset_px_r`/`offset_px_b`.
**Done criteria.** Find or construct one example with a visible
glitch/chromatic-aberration effect; confirm detection fires with a
plausible offset value, and does not fire on normal (non-glitched) shots
(check a compressed/re-encoded shot too, since compression artifacts can
introduce spurious tiny channel misalignment — make sure the noise floor
threshold is set high enough to exclude that, per spec §8.3's
"compression artifacts" failure mode).
**Dependencies.** Unit 1.4 (shot segmentation).

### Unit 1.16 — Grade statistics (descriptive only)
**Scope.** Implement `signals/effects.py::grade_stats()`. Descriptive
stats only — see `DESIGN_NOTES.md` §8, this must NOT synthesize or return
a LUT.
**Implementation.** Per shot, sample a handful of frames (e.g. 5 evenly
spaced). Compute: `contrast` = ratio of the frame's luminance std-dev to a
neutral reference std-dev (pick a fixed reference value representing
"normal" contrast, e.g. calibrate against a few unedited reference clips);
`saturation` = mean saturation channel value in HSV space relative to a
neutral reference; `temp` = a proxy for color temperature shift, e.g. the
difference between mean red-channel and mean blue-channel values
(positive = warm shift, negative = cool shift), scaled to roughly match
the ~-500..500 Kelvin-ish range implied by the spec's example
(`"temp": 200`) — exact scale is a judgment call, document whatever
constant you pick as a comment so it's not a mystery number later. Always
construct `Grade(lut_available=False)`.
**Done criteria.** Run on 3-5 shots with visibly different grades (e.g. a
warm/high-saturation shot vs. a neutral one) and confirm the numbers move
in the expected direction (warm shot → higher `temp`; punchy shot → higher
`contrast`/`saturation`). No absolute accuracy bar — this is a relative
signal, not a colorimetrically-calibrated measurement.
**Dependencies.** Unit 1.4 (shot segmentation).

### Unit 1.17 — Trace builder integration
**Scope.** Implement `signals/trace_builder.py::build_trace()`, wiring
every prior unit together into one validated `EditTrace`. This is pure
integration — no new detection logic.
**Implementation.** Enforce the ordering constraints already documented in
the module docstring:
1. `mask_watermark_regions` (1.3) runs first; its output frames feed both
   `motion` (1.6) and `text` (1.7-1.11).
2. `audio.transcribe` (1.10) and `audio.separate_speech_music` (1.11) must
   complete before `text.classify_role` (1.11) is called.
3. `cuts.detect_cuts` (1.4+1.5) must complete before
   `audio.compute_beat_lock` (1.12) (needs `cut_times_s`).
Failure policy: if any sub-extractor raises, let it propagate (fail
loudly) EXCEPT where a unit's own docstring specifies a None-on-absence
contract (the effects detectors) — a `None` return from an effects
detector is expected/normal and should simply not be appended to
`Shot.effects`, it is not an error condition.
**Done criteria.** `build_trace()` run against all annotated golden videos
(from Unit 0.3 and any added since) produces a valid `EditTrace` for each
— i.e., `EditTrace.model_validate(...)` doesn't raise — with no crashes.
This is the first point where the full L1 pipeline runs end-to-end on a
real video.
**Dependencies.** All of Units 1.1-1.16.

### Unit 1.18 — CLI wiring
**Scope.** Implement `cli/analyze.py::main()`.
**Implementation.** Parse `source` (path or URL) and `--out`. If `source`
looks like a URL (starts with `http`), call `ingest.downloader.fetch()`
first (catching `UnsupportedSourceError` and printing a clear message
telling the user to upload the file instead — per the ingest policy, a
download failure must never look like a fatal crash). Otherwise treat
`source` as a local path directly. Call `ingest.cache` to check for a
cached trace by content hash before re-running normalize+build_trace (Unit
1.2). Call `ingest.normalize.normalize()`, then
`signals.trace_builder.build_trace()`, then write
`trace.model_dump_json(indent=2)` to `--out`.
**Done criteria.** `python -m cli.analyze <some_local_mp4> --out
trace.json` runs to completion on a real file and produces a valid,
readable JSON file. Running it a second time on the same file completes
near-instantly (cache hit, per Unit 1.2).
**Dependencies.** Units 1.1-1.2, 1.17.

### Unit 1.19 — Eval harness + Phase 1 gate
**Scope.** Implement `eval/metrics.py` (all functions) and `eval/run.py`,
and finish annotating the golden set up to at least 20 videos (spec §11's
Phase 1 gate size) across the 5 genres named in spec §12 (talking head,
product, dance/trend, text-heavy tutorial, cinematic b-roll — aim for at
least 3-4 of each). Videos annotated via Unit 0.4's project-file importer
count toward this 20, but cap how much the gate leans on them: that path
gives cut/transition ground truth for free but only best-effort (often
absent) text-layer ground truth, so keep at least half the 20 as fully
hand-annotated (either from scratch or a project-file draft a human has
completed the `text_layers` section of by watching the video) — otherwise
the `text_layer_timing_iou` gate is being measured on an artificially thin
sample and a regression there could hide until much later.
**Implementation.**
- `cut_boundary_f1()`: for each predicted cut, it's a true positive if a
  ground-truth cut exists within `tolerance_frames` (default 2) of it and
  hasn't already been matched to another prediction (one-to-one greedy
  matching by nearest time); unmatched predictions are false positives,
  unmatched ground-truth cuts are false negatives. Standard
  precision/recall/F1 from there.
- `transition_type_accuracy()`: accuracy over the matched true-positive
  pairs only (a cut that wasn't detected at all can't have a "correct
  type").
- `text_layer_timing_iou()`: for each predicted layer matched to its
  best-overlapping ground-truth layer (by string similarity first, to
  avoid matching the wrong layer, then by temporal IoU), compute temporal
  IoU (`overlap / union` of `[t_in, t_out]` intervals); average across
  matched layers.
- `text_layer_cer()`: standard character error rate (Levenshtein distance
  / ground-truth string length) on matched layer pairs.
- `beat_lock_offset_error()`: simple absolute difference in frames.
- `motion_primitive_accuracy()`: accuracy over shots where ground truth
  specifies a primitive.
- `eval/run.py::main()`: loads every `eval/golden/<id>/annotations.json`,
  runs `build_trace()` fresh (or from cache) on each, computes all metrics
  above, prints a summary table, writes a JSON report to
  `eval/reports/<timestamp>.json`, and compares against
  `eval/reports/baseline.json` if it exists — exits non-zero if any metric
  regresses beyond a small tolerance band (define per-metric, e.g. 2
  percentage points) once a baseline exists (first run has no baseline to
  compare against — just establish one).
**Done criteria — this is the Phase 1 exit gate, unchanged from spec
§11:** `python -m eval.run` over >=20 hand-labeled golden videos reports
cut-boundary F1 >= 90% within ±2 frames AND text-layer timing IoU >= 85%.
Do not proceed to Phase 2 until both numbers are met. If they aren't,
go back and tune the specific unit responsible (most likely candidates,
in order of likely impact: Unit 1.4's `min_scene_len`/reconciliation
merge-tolerance, Unit 1.7's IoU/string-similarity thresholds and grace
window).
**Dependencies.** All of Phase 1 (Units 1.1-1.18), Unit 0.3 extended to
the full golden set.

---

## PHASE 2 — Template + render, ffmpeg-first

### Unit 2.1 — Slot derivation (mechanical, L1-only)
**Scope.** Implement `compiler/slots.py::shot_to_slot()`,
`generate_human_instruction()` (mechanical/L1-only version — no semantics
yet), `derive_duration_flex()`.
**Implementation.** `shot_to_slot()`: direct field mapping from `Shot` →
`Slot` (order = shot's position index, `duration_s` = `t_out - t_in`,
`applied.motion` = the shot's `MotionCurve` verbatim, `applied.grade_ref`
left as a placeholder string id for now since grade isn't applied in v1
per `DESIGN_NOTES.md` §8, `applied.out_transition` = a string id
identifying the shot's `out_transition.type` + params). `requirements`:
`needs_face` = `shot.content.has_face` if known else `False`,
`motion_pref` = bucket `shot.motion` primitive + shake into low/medium/high
(e.g. `static`→low, ramped primitives with high shake→high, else medium),
`shot_type_pref` = `[shot.content.shot_type]` if known else `[]`.
`generate_human_instruction()` mechanical template: something like
`"Drop a clip here (~{duration_s:.1f}s). {motion_desc}. {face_desc}."`
where `motion_desc`/`face_desc` are simple conditional phrases built only
from L1 facts already on the `Shot` — never invent a claim not present in
the trace. `derive_duration_flex()`: `min_s`/`max_s` = the shot duration
±25% (starting heuristic, tune later), `snap="beat"` if the shot's
`out_transition` lands within tolerance of a beat per the trace's
`beat_lock_ratio`/offsets, else `"none"`.
**Done criteria.** Given a real `EditTrace` from Phase 1, `compile_template`
(once Unit 2.3 exists) produces slots whose `human_instruction` strings
read as sensible plain English when printed — manually review all slots
for 2-3 templates; no instruction should reference a fact not visibly true
in the source video.
**Dependencies.** Phase 1 complete (needs a real `EditTrace` to operate
on).

### Unit 2.2 — Beat-snap algorithm
**Scope.** Implement `compiler/beat_snap.py::snap_duration_to_beat()`.
**Implementation.** Exactly the algorithm in the module's own docstring
(already written into the stub — implement it as specified, do not
re-derive): given `[min_s, max_s]`, `nominal_s`, `t_start_s`,
`beat_grid_s`, `median_cut_offset_frames`, `fps`: target out-point =
`t_start_s + nominal_s`; find beats within `[t_start_s + min_s,
t_start_s + max_s]`; for each candidate beat, compute
`candidate_duration = beat_time - (median_cut_offset_frames / fps) -
t_start_s`; pick the candidate whose duration is closest to `nominal_s`;
if none fall in range, return `(nominal_s, False)`.
**Done criteria.** Unit test with a synthetic beat grid and a window that
does contain a valid beat (assert snapped, correct duration) and one that
does not (assert unsnapped fallback, `was_snapped=False`). Also test that
a nonzero `median_cut_offset_frames` shifts the result versus an offset of
0 — guard against this collapsing back to naive on-beat snapping.
**Dependencies.** None beyond Phase 1's schema (pure function, can be
built independently of 2.1, but do 2.1 first per the listed order since
it's the more central piece).

### Unit 2.3 — Template compiler integration
**Scope.** Implement `compiler/template.py::compile_template()`.
**Implementation.** Iterate shots in order, call `shot_to_slot()` per
shot, assemble `Template.slots`. Build `AudioRef` from `trace.audio` —
populate `beat_grid_s`, leave `platform`/`track_title`/`artist` as `None`
unless L2 semantics (not yet available in Phase 2) can supply them;
`embed_permitted` is always `False` (type-enforced already). Collect
`confidence_flags`: append a human-readable string for every low-confidence
element encountered — font guesses below some confidence threshold (e.g.
<0.7), any `motion.primitive == "keyframed"` (residual too high to fit),
any `speed_ramp` effect (always flagged, per its detector's built-in low
confidence), grade stats present (flag that grade is NOT applied, so
downstream users aren't surprised the render looks flatter than the
original).
**Done criteria.** `compile_template(trace)` on a real Phase-1-produced
trace returns a `Template` that validates, has one slot per shot in
correct order, and a non-empty, sensible `confidence_flags` list for any
template that actually has low-confidence elements (and an empty list for
a simple, clean cut-only template — verify both cases).
**Dependencies.** Units 2.1, 2.2.

### Unit 2.4 — Render interface + manual smoke-test binding
**Scope.** Finalize `render/interface.py` (already fully specified as an
ABC — this unit is about confirming the contract is right by using it, not
changing it) and hand-write one `BindingSet` for a smoke test (a small
Python script or notebook, not a permanent file — this is throwaway
scaffolding to unblock Unit 2.5, delete it once the matcher exists in
Phase 3).
**Implementation.** No production code changes expected unless a gap is
found while trying to use the interface for a real render — if you find
you need a field on `RenderOptions`/`RenderReport` that isn't there, add
it now (this interface has had zero real usage yet, better to fix it here
than after two engines depend on the old shape).
**Done criteria.** You have a `Template` (from Unit 2.3) + a hand-built
`BindingSet` (assigning, say, 2-3 short local test clips to a template's
first few slots, leaving the rest in `unresolved_slots`) ready to hand to
Unit 2.5.
**Dependencies.** Unit 2.3.

### Unit 2.5 — ffmpeg render engine (cut-only smoke test)
**Scope.** Implement `render/engines/ffmpeg_engine.py::render()` and
`preview()`. Cut-only: honor slot durations/order and basic transitions
(hard cut, simple crossfade for `dissolve`). Explicitly out of scope:
kinetic text, punch-in/pan motion, any of the `effects_library`
primitives beyond a plain crossfade — all of that degrades to nothing and
gets logged as an approximation. This engine exists to prove the
Template→render pipeline shape, not to produce a good-looking video.
**Implementation.** Build an ffmpeg filtergraph: for each bound slot, trim
the source asset to the slot's duration starting at the matcher's
`in_point_s` (or, for this smoke test, a hardcoded 0), scale/pad to
`opts.resolution`, concatenate in slot order using the `concat` filter (or
successive `xfade` filters for `dissolve` transitions). Unresolved slots
render as a solid color placeholder frame of the correct duration (so the
timeline length still matches the template) with a burned-in text overlay
like "MISSING: slot_03" — never silently skip a slot. Populate
`RenderReport.approximations` with one entry per slot noting what was
degraded (e.g. "slot_02: punch_in motion not rendered by ffmpeg engine").
**Done criteria.** Given the Unit 2.4 smoke-test `BindingSet`, `render()`
produces a playable MP4 of the correct total duration with clips in the
correct order, and `preview()` produces a storyboard image. Play it back
and visually confirm slot order/durations are right (motion/text quality
is NOT being judged here — that's Phase 2's later gate on the Remotion
engine).
**Dependencies.** Unit 2.4.

### Unit 2.6 — Effects library primitive contracts
**Scope.** Implement `render/effects_library/primitives.py::
nearest_fallback_primitive()`. The `PRIMITIVE_PARAM_CONTRACTS` dict is
already complete in the stub — this unit is just the fallback-lookup
function.
**Implementation.** Hardcode a small similarity/fallback table, e.g.:
`slow_push`→`punch_in` (both are scale ramps), `zoom_out_reveal`→`punch_in`
(inverse direction, closest available), `whip_pan`→`pan` (whip is a fast
pan), unknown effects → `None`-equivalent handled by the caller as "no
motion applied, static frame for the duration." Document the table as a
simple dict literal, not an algorithm — there's no scoring needed for a
library this small.
**Done criteria.** Calling `nearest_fallback_primitive("zoom_out_reveal")`
returns `"punch_in"` (or your chosen mapping) and every primitive name
that appears in `MotionPrimitive`/effect types has SOME fallback entry —
write a test asserting the function never raises/returns `None` for any
value in `schemas.models.MotionPrimitive`.
**Dependencies.** None beyond Phase 1 schemas (can be done any time before
Unit 2.7 needs it).

### Unit 2.7 — Remotion engine (Node worker + Python bridge)
**Scope.** This is the largest unit in Phase 2. In scope: a working
Remotion project that can render a template's kinetic text + motion
primitives from a JSON props file, plus the Python-side subprocess bridge
in `render/engines/remotion_engine.py`. Out of scope: the OTIO export
format (deferred to Phase 3+, see `compiler/otio_export.py`'s own
docstring) and any primitives beyond the list in
`render/effects_library/primitives.py`.
**Implementation.**
- Initialize a Remotion project under a new directory `render/remotion_app/`
  (this directory does not exist yet in the scaffold — create it via
  Remotion's own project scaffolding tool, e.g. `npx create-video@latest`,
  choosing the blank/TypeScript template). This is a Node project living
  inside the Python repo; document the two-runtime nature clearly in that
  directory's own README (create one) so it's obvious `npm install` is
  needed there separately from `pip install`.
- Build one Remotion `<Composition>` whose `props` shape mirrors
  `Template` + `BindingSet` serialized to JSON exactly as Pydantic's
  `.model_dump()` would produce (snake_case field names preserved — don't
  let the Node side silently expect camelCase; either keep snake_case
  end-to-end or write one explicit, tested conversion function, not an ad
  hoc one).
- Implement one React component per entry in `PRIMITIVE_PARAM_CONTRACTS`:
  `PunchIn`, `SlowPush`, `WhipPan`, `Shake`, `Flash`, `RgbSplit`, `Freeze`,
  `SpeedRamp`, `TextPop`, `TextTypewriter`, `TextWordByWord`,
  `CaptionKaraoke`. Each takes exactly the params listed in
  `PRIMITIVE_PARAM_CONTRACTS[name]` — treat that dict as the literal
  TypeScript prop-type source (write the TS interfaces to match it 1:1).
  Use Remotion's `interpolate()`/`spring()` helpers for easing — map
  `Easing` enum values (`linear`, `easeIn`, `easeOut`, `easeInOut`,
  `spring`) directly to Remotion's built-in easing functions of the same
  semantics.
- `render/engines/remotion_engine.py::render()`: serialize
  `(template, bindings, opts)` to a props JSON file, invoke
  `npx remotion render <entry-point> <composition-id> <output.mp4>
  --props=<props.json>` via `subprocess.run`, capture stdout/stderr, raise
  on non-zero exit. Populate `RenderReport.approximations` from
  `Template.confidence_flags` plus any primitive that had to use
  `nearest_fallback_primitive` (log this from the TS side into a
  side-channel JSON file the Python side reads after render, e.g. Remotion
  writes `render_log.json` alongside the output).
**Done criteria.** The same Unit-2.4-style `BindingSet` (or a richer one
covering a template with text layers) renders via `RemotionEngine` to a
playable MP4 where: cuts happen at the right times, at least `punch_in`
and one text animation primitive are visibly correct when played back.
This does not need to hit the Phase 2 blind-viewer bar yet (that's Unit
2.9) — this unit's bar is "the Node bridge works end-to-end for a
non-trivial template."
**Dependencies.** Units 2.4, 2.6. Requires Node.js + npm installed
separately from the Python environment (note this in the new
`render/remotion_app/README`).

### Unit 2.8 — Render report assembly
**Scope.** Consolidate render-report construction so both
`FfmpegEngine` and `RemotionEngine` populate `RenderReport.approximations`
consistently (same phrasing conventions, e.g. always
`"{slot_id}: {what was approximated}"`), so a downstream consumer (MCP
tool response, eventual UI) doesn't need per-engine special-casing.
**Implementation.** Extract a small shared helper (e.g. a function in
`render/interface.py` or a new `render/report.py` if that's cleaner) that
both engines call to append a standardized approximation entry, given
`(slot_id, reason)`. Retrofit both engines from Units 2.5/2.7 to use it.
**Done criteria.** Rendering the same template through both engines
produces `RenderReport.approximations` entries in the same format
(diffable/comparable), even though the actual content differs (ffmpeg
will have far more entries than Remotion).
**Dependencies.** Units 2.5, 2.7.

### Unit 2.9 — Blind-viewer eval, Phase 2 gate
**Scope.** Run the spec §11 Phase 2 human evaluation protocol using
`RemotionEngine` output.
**Implementation.** Pick 10 templates from the golden set (Phase 1
output, compiled via Units 2.1-2.3). For each, hand-assign real
placeholder clips (not the matcher — that's Phase 3) to every slot,
render via `RemotionEngine`, and show the original + re-creation pair to
5 blind viewers who rate "is this the same edit?" on a 1-5 Likert scale
without being told which is which. Record every score alongside that
template's `render_report`/`confidence_flags` so a low score can be
traced back to a specific approximation.
**Done criteria — Phase 2 exit gate, unchanged from spec §11:** average
rating >= 4/5 across the 10 templates. If not met, look at whether low
scores correlate with specific flagged approximations (e.g. templates
with a `speed_ramp` flag scoring systematically lower) — that tells you
which render primitive most needs work before moving to Phase 3, rather
than guessing.
**Dependencies.** Units 2.1-2.8.

---

## PHASE 3 — Semantics + matcher

### Unit 3.1 — Evidence gate (build before any provider exists)
**Scope.** Implement `semantics/gating.py::allowed_labels_for_shot()` and
`validate_annotation()`. Deliberately built and unit-tested BEFORE Unit
3.3's provider call exists, so the "VLM invents effects" failure mode
(spec §8.3) is caught by tests against synthetic model output, not
discovered against a real (expensive, slow) model call.
**Implementation.** `allowed_labels_for_shot()`: from a `Shot`, compute
the set of legal effect-type strings (from `shot.effects`), the legal
transition-type strings (from `in_transition`/`out_transition`), and the
legal motion-primitive string (from `shot.motion.primitive`) — union all
into one allowlist set. `validate_annotation()`: given a
`SemanticShotAnnotation` and an allowlist, check every claim field against
it; if `annotation.role` or any other field implies an effect/primitive
not in the allowlist, raise `EvidenceViolation` (caller — Unit 3.4 —
catches this per-shot).
**Done criteria.** Unit tests in `tests/test_gating.py` (new file)
constructing a `Shot` with, say, only a `freeze` effect, then feeding a
`SemanticShotAnnotation` that (in some encoded way — extend the test to
actually exercise a field that carries an effect claim, e.g. if
`role`-string-matching against effects is how violations get encoded in
your implementation) asserts a `glitch`/`rgb_split`-implying claim not
present in the shot → confirm `EvidenceViolation` is raised. Also test the
inverse: a `SemanticShotAnnotation` with only evidence-backed claims
passes through unchanged.
**Dependencies.** Phase 1 complete (needs real `Shot`/`EditTrace` shapes,
though tests can use hand-constructed ones without running the full
pipeline).

### Unit 3.2 — Evidence pack builder
**Scope.** Implement `semantics/evidence_pack.py::build_evidence_pack()`.
**Implementation.** For each shot, extract first/middle/last frame from
the normalized video at the shot's `t_in`/midpoint/`t_out`, tile them
horizontally into one image (e.g. via `PIL.Image` compositing), burn in
the timestamp text on each tile (`cv2.putText` or PIL's `ImageDraw`).
Cache these per `(content_hash, shot_id)` under
`{cache_root}/{hash}/contact_sheets/{shot_id}.png` so re-running semantics
after a model upgrade doesn't re-render them (a pure image-composition
step, not worth re-doing). Also produce one low-res, whole-video tiled
sheet (e.g. one frame every ~1s, tiled into a grid) for the triage pass.
**Done criteria.** Given a real trace + normalized video, running this
produces one contact-sheet PNG per shot plus one whole-video sheet, all
readable/reviewable by opening them manually, with visibly burned-in
timestamps matching the trace's `t_in`/`t_out`.
**Dependencies.** Phase 1 complete (needs `EditTrace` + normalized video).

### Unit 3.3 — Anthropic provider: triage pass
**Scope.** Implement `semantics/providers/anthropic_provider.py::
AnthropicProvider.triage()` only (not `deep_pass()` — that's Unit 3.4).
Before writing this, consult the `claude-api` skill/reference for the
current model id and structured-output/tool-use pattern — do not
hand-guess a `model_id` string, and pin whatever you find exactly
(`AnthropicProvider.model_id = "<exact pinned string>"`).
**Implementation.** Send the whole-video low-res contact sheet (Unit 3.2)
plus `duration_s`/`tempo_bpm` as a structured prompt requesting JSON
matching `StyleSummary`'s shape (genre, hook_type, pacing_description).
Use Anthropic's structured-output mechanism (tool-use/JSON mode, per the
claude-api reference) rather than free-text parsing. Record the exact
model_id used in the returned `StyleSummary.model_id`.
**Done criteria.** Running `triage()` against 3-5 real videos produces a
`StyleSummary` that validates against the schema and reads as a plausible
(even if not perfect) description when you compare it to the actual video.
**Dependencies.** Unit 3.2, and the `claude-api` skill's current guidance
on model id/structured output.

### Unit 3.4 — Anthropic provider: deep pass + repair-retry
**Scope.** Implement `AnthropicProvider.deep_pass()` and
`semantics/gating.py::repair_or_fail()`.
**Implementation.** `deep_pass()`: send one shot's contact sheet +
`allowed_effect_labels` (from Unit 3.1's `allowed_labels_for_shot`,
computed by the CALLER and passed in via `DeepPassPromptInputs` — the
provider itself does not compute the allowlist) + OCR strings + transcript
snippet, explicitly instructing the model in the prompt that it may only
select from `allowed_effect_labels` for any effect-related claim (this is
prompt engineering enforcing the same rule the code enforces after the
fact — both layers matter, per spec §4.3). Request structured JSON
matching `SemanticShotAnnotation`. `repair_or_fail()`: validate the raw
JSON against the Pydantic schema; on `ValidationError`, retry once with a
prompt that includes the validation error message and asks the model to
correct its output; on a second failure, raise (do not silently drop or
guess-fill fields).
**Trigger policy (lives in the semantics package's top-level orchestration,
not inside the provider):** call `deep_pass()` only for shots where L1
confidence is genuinely low (e.g. `motion.residual` above the keyframe
threshold, or `content.shot_type is None`) OR where content labeling is
needed for a role the compiler wants (per spec §4.2) — do not call it for
every shot unconditionally, that defeats the two-pass cost structure.
**Done criteria.** For a shot with a deliberately narrow evidence set
(e.g. only a `freeze` effect, no motion primitive beyond `static`),
running `deep_pass()` end-to-end through `gating.validate_annotation()`
never produces an annotation claiming an effect outside that set — if the
raw model output ever tries to, confirm it gets caught (either by the
repair retry producing a corrected response, or by
`EvidenceViolation` on the second attempt, never silently passed through).
**Dependencies.** Units 3.1, 3.2, 3.3.

### Unit 3.5 — Rich human_instruction generation
**Scope.** Extend `compiler/slots.py::generate_human_instruction()` to
prefer the semantic annotation's `role`/content description when
available (Unit 3.4's output), falling back to the Unit 2.1 mechanical
version when no annotation exists for a shot.
**Implementation.** When `annotation is not None` and passed evidence
gating, compose a more natural instruction using `annotation.role` (e.g.
"This is your hook shot — drop a close-up reaction, ~1.2s, with visible
motion.") instead of the generic mechanical phrasing. Still constrained:
never state a fact not present on the `Shot` itself or the validated
annotation — the annotation has ALREADY been evidence-gated by Unit 3.1
by the time it reaches this function, so this function can trust it, but
should not introduce NEW unvalidated claims of its own.
**Done criteria.** Re-run the manual review from Unit 2.1 on 2-3 templates
now compiled with semantics available; confirm the richer instructions
read noticeably more useful/specific than the mechanical ones, with no
new fabricated claims.
**Dependencies.** Units 2.1, 3.4.

### Unit 3.6 — Matcher: asset probing
**Scope.** Implement `matcher/probe.py::extract_asset_features()`.
**Implementation.** Delegate duration/orientation/fps to
`ingest.probe.probe_media()` (Phase 1's ingest probe, reused here rather
than reimplemented). Face detection: a lightweight detector is sufficient
(e.g. `cv2.CascadeClassifier` with a Haar face cascade, or `mediapipe`
face detection if already a dependency elsewhere — pick one and pin it).
Shot-type guess: a coarse heuristic from face bbox size relative to frame
(large face bbox → closeup, small/no face → wide/medium) is an acceptable
v1 approximation — do not build a full shot-type classifier model for
this. Motion score: reuse `signals.motion.estimate_affine_motion`'s
inlier-based magnitude or a simple frame-diff energy measure across the
asset. CLIP embedding: `open_clip` or `clip` package,
`model.encode_image()` on a representative sampled frame (e.g. the
temporal midpoint), L2-normalized. Speech presence: reuse
`signals.audio.transcribe` and check if any words were returned above a
confidence floor.
**Done criteria.** Running this against 5-10 varied local test clips
(different orientations, with/without faces, with/without speech)
produces plausible `AssetFeatures` for each — spot check by eye.
**Dependencies.** Phase 1's `ingest.probe` and `signals.motion`/`signals.audio`
modules (reused, not reimplemented).

### Unit 3.7 — Matcher: scoring function
**Scope.** Implement `matcher/score.py::score_pair()` and
`cost_matrix()`, using the `SCORE_WEIGHTS` already defined in the stub as
the starting point.
**Implementation.** `score_pair()`: `clip_similarity` = cosine similarity
between the asset's CLIP embedding and a role-exemplar embedding — build a
small fixed set of exemplar embeddings up front (e.g. embed a handful of
reference images/text prompts per common role like "hook"/"reveal"/
"reaction" using CLIP's text encoder against role names, since you won't
have curated exemplar images initially — `open_clip`'s text-image joint
embedding space allows scoring an image against a text prompt directly,
which is simpler to bootstrap than sourcing exemplar images). `face_match`
= 1.0 if `requirements.needs_face == asset.has_face`, 0.5 if
`requirements.needs_face` is `False`/unset (no constraint), 0.0 if
`needs_face=True` and asset has no face. `shot_type_match` = 1.0 if
`asset.shot_type_guess` is in `requirements.shot_type_pref` (or the pref
list is empty), else a partial credit scheme (e.g. 0.5) rather than a hard
0 — shot-type guesses are approximate on both sides. `motion_pref_match`
similarly bucketed. Combine via the documented weights.
`cost_matrix()`: `1 - score_pair(...)` for every (asset, slot) pair.
**Done criteria.** Unit test with a hand-constructed asset/requirements
pair that should obviously score high (matching everything) and one that
should score low (mismatched on every dimension) — confirm the ordering
is right, don't chase a specific numeric value yet (tuning against human
ratings is Unit 3.9's job).
**Dependencies.** Unit 3.6.

### Unit 3.8 — Matcher: assignment + in-point + beat-snap
**Scope.** Implement `matcher/assign.py::pick_in_point()` and
`match_assets()`.
**Implementation.** `match_assets()`: build the cost matrix (Unit 3.7),
solve with `scipy.optimize.linear_sum_assignment` — but that function
assumes a square matrix and no reuse cap, so handle the
`max_asset_reuse_count` constraint by replicating each asset's cost-matrix
row up to `max_reuse` times (as if it were `max_reuse` virtual copies of
the same asset) before calling the solver, then map assignments back to
the original asset id afterward. `pick_in_point()`: within the chosen
asset, slide a window of the slot's required duration across the asset in
some step size (e.g. 0.1s), scoring each window by the same motion/quality
proxy used in Unit 3.6, and pick the highest-scoring window's start time;
then call `compiler.beat_snap.snap_duration_to_beat()` (Unit 2.2 — reuse,
do not reimplement) to adjust the out-point against the template's
`beat_grid_s`/`median_cut_offset_frames`. Confidence floor: if a slot's
best-available score (after assignment) falls below a threshold (start at
0.4), move it to `unresolved_slots` instead of forcing the assignment —
never silently misplace a clip, per spec §6's explicit rule. Every
returned `AssetBinding` must have a non-empty `rationale` string
explaining the assignment in plain language (e.g. "closest CLIP match for
role=hook, face present as required").
**Done criteria.** Given 5-8 test assets and a template with slots
requiring a mix of face/no-face and different roles, `match_assets()`
produces a `BindingSet` where face-requiring slots get face-containing
assets when available, no asset is used more than `max_asset_reuse_count`
times, and at least one deliberately-impossible-to-satisfy slot (e.g. a
`needs_face=True` slot when no test asset has a face) ends up in
`unresolved_slots` rather than force-assigned.
**Dependencies.** Units 3.6, 3.7, 2.2.

### Unit 3.9 — Re-run blind-viewer eval with auto-matching
**Scope.** Repeat Unit 2.9's protocol, but with assets auto-assigned by
Unit 3.8's matcher instead of hand-assigned.
**Implementation.** Same 10 templates (or a fresh comparable set), same 5
blind viewers if feasible, same Likert protocol. Use a pool of real
candidate clips per template (varied enough that the matcher has real
choices to make, not just one obviously-correct clip per slot).
**Done criteria.** Choose a margin against Phase 2's hand-assigned score
BEFORE looking at the number (e.g. "auto-matched score should be within
0.5 points of hand-assigned") — this is called out explicitly so you're
not rationalizing after seeing the result. If the margin isn't met, the
next thing to inspect is `SCORE_WEIGHTS` tuning (Unit 3.7) against
which slots got low-confidence or wrong assignments in this run.
**Dependencies.** Units 3.6-3.8, Unit 2.9's baseline numbers.

---

## PHASE 4 — MCP server

### Unit 4.1 — Job store + FastAPI skeleton
**Scope.** Implement enough of `api/main.py` and `api/workers.py` to
support the async job_id pattern: an `analyze_video` job and a `render`
job, each backed by a Celery/RQ task, with status polling. This is
infrastructure MCP tools will wrap in Unit 4.2 — build and test it
directly via HTTP/CLI first, before MCP is in the loop, so a job-store bug
isn't confused with an MCP-transport bug.
**Implementation.** Redis-backed job store: `job_id` → `{status: pending|
running|done|error, progress: float, stage: str, error: str|None,
result_refs: dict|None}`, simple key-value via `redis-py`. Celery task
`analyze_video_task` calls Unit 1.18's pipeline functions directly (ingest
→ trace_builder → optionally semantics/compiler if `depth="full"`),
updating the job store at each stage boundary. `render_task` similarly
wraps Phase 2/3's render call. FastAPI endpoints are thin: POST to
enqueue, GET to poll — this can be minimal, it exists to prove the queue
works, not to be the final product API surface.
**Done criteria.** Enqueue an analyze job via a direct Python call (or a
quick `curl`/test client call to the FastAPI endpoint), poll until
`status=="done"`, confirm `result_refs` points at a real trace file.
**Dependencies.** Phases 1-3 (needs the actual pipeline functions to
wrap).

### Unit 4.2 — MCP tools: analysis group
**Scope.** Implement `mcp/tools.py::analyze_video()`, `get_job()`,
`get_trace()`. Out of scope in this unit: template/asset/render tools
(4.3, 4.4).
**Implementation.** Each function is a thin call into Unit 4.1's job
store/Celery tasks — `analyze_video()` enqueues and returns `{job_id}`
immediately (never blocks). `get_trace()` must paginate by `sections`
param — if `sections` is provided, return only those top-level `EditTrace`
fields; if omitted, return a summary (e.g. shot count, duration, evidence
metadata) plus a `recut://trace/{job_id}` resource URI, NOT the full
trace body (spec §9.4's explicit rule: never return a full trace by
default). Any OCR string appearing anywhere in a `get_trace` response
(e.g. inside `text_layers`) must be routed through
`wrap_untrusted_text()` before being returned.
**Done criteria.** From a Python test client (not yet a real MCP client),
call `analyze_video` → poll `get_job` to completion → call `get_trace`
with no `sections` arg (confirm it's small/summary-shaped) and with
`sections=["shots"]` (confirm only shots come back, and any text strings
within are wrapped).
**Dependencies.** Unit 4.1.

### Unit 4.3 — MCP tools: template/slot/asset/binding group
**Scope.** Implement `get_template()`, `describe_template()`,
`list_slots()`, `register_assets()`, `match_assets()`, `bind()`.
**Implementation.** `get_template()`: wraps Phase 2/3's `compile_template`
output, `format` param selects serialization (`recut` = native JSON,
`otio`/`remotion` deferred until `compiler/otio_export.py` and the
Remotion props serializer exist — for now, if `format` isn't `recut`,
raise a clear "not yet implemented" error rather than silently returning
the wrong format). `describe_template()`: human-readable breakdown built
from `Template.slots[*].human_instruction` — this is literally "the read
the edit feature," keep it simple, just formats the instructions plus the
style summary if semantics ran. `register_assets()`: accept file paths/
upload ids, run Unit 3.6's `extract_asset_features`, store keyed by a
generated `asset_id`, return the ids. `match_assets()`/`bind()`: call
Unit 3.8's `match_assets()`, then persist the chosen/user-overridden
`BindingSet` keyed by a generated `binding_id`.
**Done criteria.** End-to-end from a test client: register 3-5 local test
assets, call `match_assets` against a real template, confirm proposed
bindings + confidences come back, call `bind` with the user accepting (or
overriding) them, confirm a `binding_id` is returned and retrievable.
**Dependencies.** Units 4.2, Phase 2/3's compiler and matcher.

### Unit 4.3b — Template mutation (`adjust_template`)
**Scope.** Implement `compiler/template.py::adjust_template()` (pure
function, no MCP/business-logic mixed in — the actual math, testable
without a running server) and the corresponding
`mcp/tools.py::adjust_template()` thin wrapper. Added while designing L7
(see `DESIGN_NOTES.md` §15.4): the existing tool surface (Units 4.2-4.4)
lets an agent *bind assets* and *render*, but has no lever for "make this
punchier" or "recreate this edit style but slower" — every other example
request in the L7 requirement maps onto an existing tool ("swap the clip
in slot 3" → `bind`); this one didn't, so it's added here rather than left
as a silent gap. Useful from any MCP client, not just L7's chat loop — this
unit belongs in Phase 4, not Phase 4.5.
**Implementation.**
- Add `Template.derived_from: Optional[str] = None` to `schemas/models.py`
  (lineage — an adjusted template is a NEW template, never an in-place
  mutation of the source). Regenerate the JSON schema per Unit 0.2's
  discipline (`python schemas/generate_json_schema.py`, review the diff).
- `compiler/template.py::adjust_template(template: Template, changes:
  TemplateAdjustment) -> Template` where `TemplateAdjustment` (new
  dataclass in `compiler/schemas.py` or inline in `template.py` — small
  enough not to need its own file) is a **small, fixed, validated
  vocabulary**, not free-form: `global_duration_scale: float | None`
  (bounded, e.g. reject outside `[0.5, 2.0]` — raise `ValueError` rather
  than silently clamping, so a caller passing a nonsense value finds out
  immediately), `energy_bias: Literal["punchier", "calmer"] | None`,
  `slot_overrides: dict[str, dict] | None`. This is the L3-level analogue
  of evidence gating: the caller (human, MCP agent, or L7's chat model)
  picks a knob from this constrained schema; this function computes the
  actual new numbers — the caller never supplies a raw `duration_s`.
  - `global_duration_scale`: for every slot, multiply `duration_s` and both
    `duration_flex.min_s`/`max_s` by the scale factor, then re-run
    `compiler/beat_snap.py::snap_duration_to_beat()` (Unit 2.2 — reuse, do
    not reimplement) against the template's `audio_ref.beat_grid_s` so the
    rescaled durations still land on beats where possible.
  - `energy_bias="punchier"`: for every slot, set `duration_s` toward
    `duration_flex.min_s` (e.g. move 50% of the way from current to min,
    not straight to min — a starting heuristic, tune later) and bump
    `requirements.motion_pref` one bucket toward `"high"` if not already
    there. `"calmer"` is the mirror (toward `max_s`, bucket toward `"low"`).
    Neither ever adds a motion primitive or effect the shot doesn't already
    have — this only remaps existing fields, never invents new evidenced
    claims (the "LLM never measures" rule extended to L3 math).
  - `slot_overrides`: per-slot dict of the same two knobs, applied after
    the global ones, for slot-specific correction.
  - Returns a new `Template` with a freshly generated
    `source_trace_hash`-preserving copy (same trace, different template
    id/lineage) and `derived_from = source_template.template_id` (add a
    `template_id` field alongside `source_trace_hash` if one doesn't
    already exist by this point — check `schemas/models.py` first, this
    may already be needed for Unit 4.3's `get_template`/`describe_template`
    keying and just not surfaced yet).
- `mcp/tools.py::adjust_template(template_id: str, changes: dict) ->
  dict`: thin wrapper — load the template by id, construct
  `TemplateAdjustment` from `changes` (raise a clear validation error, not
  a stack trace, on an unknown key or out-of-range value), call
  `compiler.template.adjust_template()`, persist the result, return
  `{"new_template_id": ...}`.
**Done criteria.** Unit test: given a real compiled `Template`,
`global_duration_scale=1.25` produces a new template whose slot durations
are all ~25% longer (within beat-snap tolerance) and whose
`derived_from` points at the source; `energy_bias="punchier"` on a
template with mixed `motion_pref` values measurably shifts durations
shorter and motion_pref buckets upward without adding any effect not
already present on the source shots (assert this explicitly — it's the
regression this unit exists to prevent). `adjust_template(template_id,
{"global_duration_scale": 99})` (out of the `[0.5, 2.0]` bound) raises a
clear validation error via the MCP wrapper, not a silent clamp.
**Dependencies.** Units 2.2, 2.3, 4.3.

### Unit 4.4 — MCP tools: render/library group
**Scope.** Implement `preview()`, `render()`, `get_render()`,
`search_library()`.
**Implementation.** `render()` requires `idempotency_key` — store a
mapping `idempotency_key → job_id` in the job store so a retried call with
the same key returns the existing job instead of enqueueing a duplicate
render (spec §9.4: agents retry). `get_render()` returns `{url,
render_report}` once done — `render_report` should surface
`RenderReport.approximations` verbatim. `search_library()`: for Phase 4,
this can return an empty result set or search only over
already-user-analyzed templates in the local job store — the actual
seeded library is Phase 5's job (per `DESIGN_NOTES.md`'s "user-analyzed
only in v1" default), don't block this unit on that.
**Done criteria.** Full end-to-end MCP-tool-level flow (still via direct
Python/test-client calls, not a real MCP client yet): analyze → template →
register assets → match → bind → render (with a retried duplicate call
using the same `idempotency_key` confirmed to NOT create a second render
job) → get_render returns a playable URL + report.
**Dependencies.** Unit 4.3.

### Unit 4.5 — Resources + prompts
**Scope.** Implement `mcp/resources.py::get_resource()` and author the
three prompt templates (`recreate_this_edit`, `explain_this_edit`,
`find_similar_template`) as actual prompt text files (e.g. under a new
`mcp/prompts/` directory, one `.md` per prompt) rather than inline
strings.
**Implementation.** `get_resource()`: parse the `recut://{type}/{id}` URI
scheme, dispatch to the trace/template/render store accordingly, return
raw bytes (JSON or video bytes depending on type). Prompt files: write
each as a short instruction template describing, from the calling agent's
perspective, what tool-call sequence accomplishes the named task (e.g.
`recreate_this_edit` should walk an agent through analyze → template →
register → match → bind → render in prose, referencing the actual tool
names) — these are genuinely prompt-engineering artifacts, write them with
the same care as a system prompt, per spec §9.4's "tool descriptions are
prompt engineering" rule.
**Done criteria.** `get_resource("recut://trace/<job_id>")` returns the
full trace bytes for a completed job (this is the "full trace, but only
when explicitly fetched" path that complements Unit 4.2's summary-only
default). Each prompt file reads as a coherent, correct set of
instructions when you (a human) follow it manually against the tool
surface built so far.
**Dependencies.** Units 4.2-4.4.

### Unit 4.6 — stdio server + real client dogfood
**Scope.** Implement `mcp/server.py::run_stdio_server()`, registering
everything from Units 4.2-4.5 on the official MCP SDK's stdio transport.
**Implementation.** Follow the official Python (or TS) MCP SDK's
tool/resource/prompt registration API directly — this is SDK
boilerplate, not novel design; the design decisions were already made in
Units 4.2-4.5, this unit is wiring.
**Done criteria — this is the Phase 4a exit gate:** connect a real MCP
client (Claude Code, Claude Desktop, or Cursor) to the local server and
successfully drive the full flow (analyze → describe → register → match →
bind → render → get result) through natural conversation, without
touching a CLI or writing a test script. Note any tool description that
confused the client during this dogfood session and fix the description
text (not the underlying function) per spec §9.4.
**Dependencies.** Units 4.2-4.5.

### Unit 4.7 — Hosted HTTP + OAuth (Phase 4b, separate exit gate)
**Scope.** Implement `mcp/auth.py::verify_token()` and
`mcp/server.py::run_http_server()`.
**Implementation.** Use the MCP SDK's Streamable HTTP transport support
plus a standard OAuth 2.1 flow (authorization code + PKCE) — this is
mostly SDK/library wiring against whatever auth provider you choose (or a
minimal self-hosted OAuth server if none is chosen); no novel design
decisions here beyond picking the provider.
**Done criteria.** The same tool surface, verified working in Unit 4.6,
works identically over Streamable HTTP with a completed OAuth flow from a
hosted-mode-capable client.
**Dependencies.** Unit 4.6. Also gate this unit behind an explicit
decision to actually pursue hosted mode at all (see `DESIGN_NOTES.md` §13
— local-first is the default; only build this when hosted mode is a real
near-term goal, not speculatively).

---

## PHASE 4.5 — Conversational interface (L7)

Numbered 4.5, not folded into Phase 4 or renumbered as part of Phase 5, so
every existing cross-reference to "Phase 5"/"Unit 5.x" elsewhere in this
document stays valid (see `BUILD_ORDER.md` Phase 4.5 for the phase-level
framing and gate; this section is the unit-by-unit execution companion).
Sequenced after Unit 4.3b and Unit 4.4 — L7 imports `mcp/tools.py`'s
functions directly and calls them in-process (`DESIGN_NOTES.md` §15.1), so
those need to be real implementations by this point, not
`NotImplementedError` stubs.

### Unit 4.5.1 — Chat schemas + tool registry
**Scope.** Implement `chat/schemas.py` (dataclasses) and
`chat/tool_registry.py` (the `CHAT_TOOL_SURFACE` list). No provider code
yet — this unit only defines the shapes both the loop and every provider
adapter will consume.
**Implementation.**
- `chat/schemas.py`:
  ```python
  from dataclasses import dataclass
  from typing import Literal, Any, Callable

  @dataclass
  class ToolCall:
      id: str
      name: str
      arguments: dict[str, Any]        # already-parsed, never a raw JSON string

  @dataclass
  class ChatMessage:
      role: Literal["system", "user", "assistant", "tool"]
      content: str | None
      tool_calls: list[ToolCall] | None = None   # set on assistant messages requesting calls
      tool_call_id: str | None = None            # set on tool messages: which call this answers
      name: str | None = None                    # set on tool messages: tool name

  @dataclass
  class ToolSpec:
      name: str
      description: str                  # reused verbatim from the wrapped function's docstring
      parameters_schema: dict            # JSON Schema (Draft 2020-12), model-facing params only
      callable: Callable[..., dict]      # the actual function to invoke

  @dataclass
  class TokenUsage:
      prompt_tokens: int
      completion_tokens: int

  @dataclass
  class ChatCompletionResult:
      message: ChatMessage
      finish_reason: Literal["stop", "tool_calls", "length", "content_filter"]
      raw_model_id: str
      usage: TokenUsage | None = None
  ```
- `chat/tool_registry.py`: build `CHAT_TOOL_SURFACE: list[ToolSpec]` by
  importing `mcp.tools` and wrapping each function. Two concrete examples
  to follow exactly (write the rest of the ~12 tools — `analyze_video`,
  `get_job`, `get_trace`, `get_template`, `describe_template`,
  `register_assets`, `match_assets`, `preview`, `get_render`,
  `search_library`, `adjust_template` — the same way):
  ```python
  ToolSpec(
      name="list_slots",
      description=mcp.tools.list_slots.__doc__,
      parameters_schema={
          "type": "object",
          "properties": {"template_id": {"type": "string"}},
          "required": ["template_id"],
      },
      callable=mcp.tools.list_slots,
  )

  ToolSpec(
      name="bind",
      description=mcp.tools.bind.__doc__,
      parameters_schema={
          "type": "object",
          "properties": {
              "template_id": {"type": "string"},
              "slot_to_asset": {
                  "type": "object",
                  "additionalProperties": {"type": "string"},
                  "description": "slot_id -> asset_id",
              },
          },
          "required": ["template_id", "slot_to_asset"],
      },
      callable=mcp.tools.bind,
  )
  ```
  **`render` is a deliberate exception**: `idempotency_key` must NOT appear
  in its `parameters_schema` (a chat model has no sensible way to invent
  one, and letting it try defeats the point — spec §9A.3). Instead wrap
  `mcp.tools.render` in a small adapter function that generates
  `str(uuid.uuid4())` per invocation and passes it through positionally,
  and register *that* adapter as the `ToolSpec.callable`, e.g.:
  ```python
  def _render_tool(binding_id: str, include_audio: bool = False,
                    resolution: tuple[int, int] = (1080, 1920)) -> dict:
      return mcp.tools.render(binding_id, include_audio, resolution,
                               idempotency_key=str(uuid.uuid4()))

  ToolSpec(
      name="render",
      description=mcp.tools.render.__doc__,
      parameters_schema={
          "type": "object",
          "properties": {
              "binding_id": {"type": "string"},
              "include_audio": {"type": "boolean", "default": False},
              "resolution": {"type": "array", "items": {"type": "integer"},
                             "minItems": 2, "maxItems": 2, "default": [1080, 1920]},
          },
          "required": ["binding_id"],
      },
      callable=_render_tool,
  )
  ```
**Done criteria.** `len(CHAT_TOOL_SURFACE)` covers every tool in
`mcp/tools.py` (including Unit 4.3b's `adjust_template`) except none are
accidentally omitted (write a test that diffs the registry's tool names
against `mcp.tools`'s public function names, minus `wrap_untrusted_text`
which is a helper, not a tool). Every `parameters_schema` passes
`jsonschema.Draft202012Validator.check_schema(...)` without raising.
`render`'s schema does not contain `idempotency_key`. Every other
`ToolSpec.callable` is the *exact same function object* as in `mcp.tools`
(assert identity, e.g. `ToolSpec_for_list_slots.callable is
mcp.tools.list_slots`) — this guards against someone copy-pasting tool
logic into the registry instead of reusing it, which is the specific
anti-pattern §15.1 argues against.
**Dependencies.** Units 4.2-4.4, 4.3b (needs real tool implementations to
wrap meaningfully, though the schema/plumbing shape can be drafted against
the stubs earlier if useful).

### Unit 4.5.2 — `ChatProvider` interface
**Scope.** Implement `chat/providers/base.py`.
**Implementation.**
  ```python
  from abc import ABC, abstractmethod
  from chat.schemas import ChatMessage, ToolSpec, ChatCompletionResult

  class ChatProviderError(Exception):
      def __init__(self, message: str, *, retryable: bool):
          super().__init__(message)
          self.retryable = retryable   # loop.py's retry policy reads this

  class ChatProvider(ABC):
      model_id: str          # pinned exact string, never a floating alias
      supports_streaming: bool = False

      @abstractmethod
      def complete(self, messages: list[ChatMessage], tools: list[ToolSpec],
                   *, temperature: float = 0.3, max_tokens: int = 1024,
                   ) -> ChatCompletionResult:
          """One turn: given full message history + available tools, return
          either a tool-call request or final assistant text."""

      def stream(self, messages: list[ChatMessage], tools: list[ToolSpec], **kw):
          """Optional; default raises. See DESIGN_NOTES.md sec 15.2 -
          streaming is deferred at the method level, not the provider level."""
          raise NotImplementedError
  ```
**Done criteria.** Mirrors `semantics/providers/base.py`'s docstring
discipline (record why the interface is shaped this way). Unit test:
construct a minimal in-test subclass implementing only `complete()`,
confirm the ABC does not require `stream()` to be overridden, and confirm
instantiating `ChatProvider` directly raises `TypeError` (abstract method
not implemented).
**Dependencies.** Unit 4.5.1.

### Unit 4.5.3 — OpenAI-compatible base adapter
**Scope.** Implement `chat/providers/openai_compatible.py::
OpenAICompatibleProvider`. This is the shared adapter that Unit 4.5.4's
four concrete providers subclass/configure — get the message-conversion
logic right once, here.
**Implementation.**
  ```python
  from openai import OpenAI
  import json

  class OpenAICompatibleProvider(ChatProvider):
      def __init__(self, *, base_url: str, api_key: str, model_id: str,
                   extra_headers: dict[str, str] | None = None):
          self.model_id = model_id
          self._client = OpenAI(base_url=base_url, api_key=api_key,
                                 default_headers=extra_headers or {})

      def complete(self, messages, tools, *, temperature=0.3, max_tokens=1024):
          oa_messages = [self._to_openai_message(m) for m in messages]
          oa_tools = [{"type": "function", "function": {
              "name": t.name, "description": t.description,
              "parameters": t.parameters_schema}} for t in tools]
          try:
              resp = self._client.chat.completions.create(
                  model=self.model_id, messages=oa_messages,
                  tools=oa_tools or None, tool_choice="auto" if oa_tools else None,
                  temperature=temperature, max_tokens=max_tokens,
              )
          except Exception as e:      # openai SDK raises typed errors; map rate-limit/timeout
              raise ChatProviderError(str(e), retryable=_is_retryable(e)) from e
          choice = resp.choices[0]
          return ChatCompletionResult(
              message=self._from_openai_message(choice.message),
              finish_reason=choice.finish_reason,
              raw_model_id=resp.model,
              usage=TokenUsage(resp.usage.prompt_tokens, resp.usage.completion_tokens)
                    if resp.usage else None,
          )
  ```
  `_to_openai_message`: map `ChatMessage(role="tool", tool_call_id=...,
  name=...)` to OpenAI's `{"role": "tool", "tool_call_id": ..., "content":
  ...}` shape (content must be a string — `json.dumps` a dict tool result);
  map `role="assistant"` with `tool_calls` set to OpenAI's `{"role":
  "assistant", "tool_calls": [{"id":..., "type":"function", "function":
  {"name":..., "arguments": json.dumps(...)}}]}`.
  `_from_openai_message`: parse `choice.message.tool_calls` (if present)
  into `list[ToolCall]`, calling `json.loads(tc.function.arguments)` inside
  a `try/except json.JSONDecodeError` that re-raises as
  `ChatProviderError(..., retryable=False)` — a model emitting malformed
  JSON arguments is not something retrying the same call fixes.
**Done criteria.** Against a real OpenAI-compatible endpoint (OpenAI
itself is the simplest to verify against first), a scripted call with one
trivial `ToolSpec` (e.g. a fake `get_current_slot_count` tool backed by a
Python lambda) completes the full round trip: model requests the tool call
→ test code executes it → feeds the result back as a `role="tool"` message
→ model produces final text referencing the result.
**Dependencies.** Unit 4.5.2.

### Unit 4.5.4 — OpenAI, NVIDIA NIM, OpenRouter, vLLM concrete providers
**Scope.** Four thin subclasses/factories of `OpenAICompatibleProvider`,
plus the `Settings` fields each reads from.
**Implementation.** Add to `common/config.py::Settings` (same
"unset-pin-before-X" discipline as `triage_model_id`):
  ```python
  chat_openai_api_key: str | None = None
  chat_openai_base_url: str = "https://api.openai.com/v1"
  chat_openai_model_id: str = "unset-pin-before-4.5.4"

  chat_nim_api_key: str | None = None
  chat_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
  chat_nim_model_id: str = "unset-pin-before-4.5.4"

  chat_openrouter_api_key: str | None = None
  chat_openrouter_base_url: str = "https://openrouter.ai/api/v1"
  chat_openrouter_model_id: str = "unset-pin-before-4.5.4"
  chat_openrouter_site_url: str | None = None    # OpenRouter attribution header
  chat_openrouter_site_name: str | None = None

  chat_vllm_base_url: str | None = None          # no sane default - user's own endpoint
  chat_vllm_api_key: str = "not-needed"          # vLLM's default server doesn't check it
  chat_vllm_model_id: str = "unset-pin-before-4.5.4"
  ```
  `OpenAIProvider(OpenAICompatibleProvider)`: base_url/api_key/model_id
  from the `chat_openai_*` settings, no extra headers.
  `NvidiaNIMProvider`: same pattern with `chat_nim_*`. **Caveat, verify
  before assuming it works:** not every NIM-hosted model checkpoint
  supports function calling — check the specific model's NVIDIA model card
  for tool-calling support before pinning `chat_nim_model_id`, same
  "don't hand-guess" discipline as the `claude-api` skill note elsewhere.
  `OpenRouterProvider`: `chat_openrouter_*` settings, and
  `extra_headers={"HTTP-Referer": settings.chat_openrouter_site_url,
  "X-Title": settings.chat_openrouter_site_name}` per OpenRouter's
  attribution convention. **Caveat:** OpenRouter is a router — tool-calling
  behavior is inherited from whichever underlying model `chat_
  openrouter_model_id` selects (OpenRouter's own `vendor/model` naming,
  e.g. `"openai/gpt-..."` vs `"meta-llama/..."`); verify the selected
  model's OpenRouter listing actually advertises tool-calling support.
  `VLLMProvider`: `chat_vllm_*` settings. **Caveat, real and non-optional
  to document:** tool-calling only works if vLLM was launched with
  `--enable-auto-tool-choice --tool-call-parser <parser matching the
  served model>` (e.g. `hermes` for Qwen/Hermes-format models, `llama3_json`
  for Llama 3.x, `mistral` for Mistral-format models) — record which
  parser/model combination was actually tested in a comment next to
  `VLLMProvider`, and if tool_calls come back empty/malformed repeatedly
  for a configured model, surface a clear diagnostic (log the raw
  response) rather than treating it as "the model chose not to call a
  tool," which is a different and misleading failure mode.
**Done criteria.** Each of the 4 providers instantiable via
`build_provider()` (Unit 4.5.7) reading only from `Settings`. At minimum
OpenAI and one other (NIM or OpenRouter, whichever credential is available
at build time) complete Unit 4.5.3's round-trip test through their own
subclass. vLLM's round trip requires a locally-running vLLM instance —
if none is available at build time, explicitly note this as deferred
verification in a comment, do not mark the unit done on unverified vLLM
behavior.
**Dependencies.** Unit 4.5.3.

### Unit 4.5.5 — Gemini adapter (real adapter)
**Scope.** Implement `chat/providers/gemini.py::GeminiChatProvider`. Named
distinctly from `semantics/providers/gemini_provider.py` (different
package, different job — do not merge or import between them).
**Implementation.**
  ```python
  from google import genai
  from google.genai import types

  class GeminiChatProvider(ChatProvider):
      def __init__(self, *, api_key: str, model_id: str):
          self.model_id = model_id
          self._client = genai.Client(api_key=api_key)

      def complete(self, messages, tools, *, temperature=0.3, max_tokens=1024):
          system_text, contents = self._split_system_and_convert(messages)
          fn_decls = [types.FunctionDeclaration(
              name=t.name, description=t.description, parameters=t.parameters_schema,
          ) for t in tools]
          config = types.GenerateContentConfig(
              system_instruction=system_text,
              tools=[types.Tool(function_declarations=fn_decls)] if fn_decls else None,
              tool_config=types.ToolConfig(
                  function_calling_config=types.FunctionCallingConfig(mode="AUTO")),
              temperature=temperature, max_output_tokens=max_tokens,
          )
          resp = self._client.models.generate_content(
              model=self.model_id, contents=contents, config=config)
          return self._from_gemini_response(resp)
  ```
  `_split_system_and_convert`: pull any `role="system"` `ChatMessage`s out
  of the list into a single `system_text` string (Gemini takes this as a
  separate config field, never a message in `contents`); map remaining
  `role="user"` → `Content(role="user", parts=[Part(text=...)])`,
  `role="assistant"` (with no tool_calls) → `Content(role="model",
  parts=[Part(text=...)])`, `role="assistant"` with `tool_calls` →
  `Content(role="model", parts=[Part(function_call=...) for each call])`,
  `role="tool"` → `Content(role="user", parts=[Part(function_response=
  types.FunctionResponse(name=msg.name, response={"result": <parsed
  content>}))])` — **note this is `role="user"`, not a `tool` role; Gemini
  has no third role for this.**
  `_from_gemini_response`: iterate `resp.candidates[0].content.parts` —
  a single turn CAN contain multiple `function_call` parts, unlike OpenAI's
  list-of-tool_calls-on-one-message shape but structurally similar in
  effect; synthesize `ToolCall.id = f"{part.function_call.name}-{index}"`
  since Gemini issues no call id. `part.function_call.args` is already a
  parsed mapping (`dict(part.function_call.args)`), not a JSON string —
  do NOT call `json.loads` on it, that's an OpenAI-specific step that would
  raise here.
**Done criteria.** Same round-trip test as Unit 4.5.3, run against a real
Gemini endpoint. Additionally, since forcing a real API to return multiple
function calls in one turn on demand is unreliable, write a unit test that
mocks `genai.Client.models.generate_content` to return a fixture response
with 2 `function_call` parts in one candidate, and confirm
`_from_gemini_response` produces 2 `ToolCall`s with distinct synthesized
ids, both of which the loop (once Unit 4.5.6 exists) executes and feeds
back correctly.
**Dependencies.** Unit 4.5.2. Independent of Units 4.5.3-4.5.4 — can be
built in parallel.

### Unit 4.5.6 — Tool-calling loop + session handling
**Scope.** Implement `chat/loop.py::run_turn()` and
`chat/session.py::ChatSession`.
**Implementation.**
- Add to `Settings`: `chat_max_tool_iterations: int = 8`,
  `chat_session_ttl_s: int = 86400`.
- `run_turn(provider: ChatProvider, tools: list[ToolSpec], history:
  list[ChatMessage]) -> ChatMessage`: loop up to
  `Settings.chat_max_tool_iterations` times. Each iteration: call
  `provider.complete(history, tools)`; if the result message has no
  `tool_calls`, append it to `history` and return it (done). If it does,
  append the assistant tool-call message to `history`, then for each
  `ToolCall`: look up the matching `ToolSpec` by name, call
  `spec.callable(**call.arguments)` inside a `try/except Exception`;
  on success, wrap the result — **any string value anywhere in the result
  that originated from OCR/transcript/caption text must be passed through
  `mcp.tools.wrap_untrusted_text()` first** (reuse it, do not reimplement
  — import it directly); on failure, construct a `{"error": str(e)}`
  payload instead of letting the exception propagate (a tool error is
  information the model should get to react to, not a crashed session).
  Append one `ChatMessage(role="tool", tool_call_id=call.id, name=call.name,
  content=json.dumps(result))` per call, then continue the loop. If
  `chat_max_tool_iterations` is exhausted without a final text response,
  return a `ChatMessage(role="assistant", content="I ran into trouble
  completing that — here's what I tried: ...")` summarizing the attempted
  tool calls, rather than raising or looping forever.
- `ChatSession`: `session_id: str`, `history: list[ChatMessage]`,
  `send(user_text: str) -> str` — appends a user message, calls
  `run_turn()`, returns the final assistant text. Persistence: serialize
  `history` to JSON, store in Redis under `chat_session:{session_id}` with
  `EX=Settings.chat_session_ttl_s` (reuse the same `redis-py` client
  pattern as Unit 4.1's job store — same infra, not a new dependency).
  Load-on-init if a `session_id` is provided and found in Redis; otherwise
  start empty history with one `role="system"` message (the system prompt
  — write a short one describing RECUT's tool surface and instructing the
  model to prefer calling a tool over guessing, and to explain
  `render_report`/`confidence_flags` approximations to the user in plain
  language when relevant).
**Done criteria.** With one working provider (from 4.5.4 or 4.5.5): a
scripted conversation ("what slots does template X have?" → tool call to
`list_slots` → "put my beach clip in slot 3" → tool call to `bind`)
completes with no tool-dispatch code written by the test itself (the loop
does it). A forced-error test: a `ToolSpec` whose callable always raises
confirms the loop produces a `role="tool"` error message and the session
does not crash. A forced-runaway test: a fake `ChatProvider` whose
`complete()` always returns a tool-call request, never final text,
confirms the loop hard-stops at `chat_max_tool_iterations` and returns the
fallback message rather than looping forever. A persistence test: create a
session, send one message, construct a NEW `ChatSession` object with the
same `session_id`, confirm the reloaded history includes the prior turn.
**Dependencies.** Unit 4.5.1, at least one of Units 4.5.4/4.5.5, Unit 4.1
(Redis infra), `mcp.tools.wrap_untrusted_text`.

### Unit 4.5.7 — Provider selection + config surface
**Scope.** Implement `chat/providers/factory.py::build_provider()`.
**Implementation.** Add `chat_provider: Literal["openai", "nim",
"openrouter", "vllm", "gemini"] | None = None` to `Settings`.
`build_provider(settings: Settings) -> ChatProvider`: `match
settings.chat_provider` over the 5 cases, instantiating the corresponding
concrete class from Units 4.5.4/4.5.5 using that provider's `Settings`
fields; raise a clear `ValueError` (not an `AttributeError` from a missing
config field deep inside a provider's `__init__`) if
`settings.chat_provider` is unset, or if the selected provider's required
field is unset (e.g. `chat_provider="vllm"` but `chat_vllm_base_url is
None`) — check required fields explicitly in the factory before
constructing the provider. No code above this factory (loop, session, API
endpoint) should ever import a concrete provider class directly — only
`ChatProvider` (the ABC) and `build_provider`.
**Done criteria.** Setting `RECUT_CHAT_PROVIDER=openai` (plus its api key)
via env and calling `build_provider(load_settings())` returns an
`OpenAIProvider` instance; switching the env var to `gemini` (plus its
key) with no other code change returns a `GeminiChatProvider` instance.
Unsetting a required field for the selected provider raises `ValueError`
with a message naming the missing field, not a stack trace from inside the
provider constructor.
**Dependencies.** Units 4.5.4, 4.5.5.

### Unit 4.5.8 — Chat API endpoint
**Scope.** Add `POST /chat/{session_id}/message` (and a session-creating
variant, e.g. `POST /chat/message` returning a fresh `session_id` if none
is supplied) to `api/main.py`.
**Implementation.** Thin FastAPI endpoint: load or create a `ChatSession`
(Unit 4.5.6) for the given `session_id`, using `build_provider(load_
settings())` (Unit 4.5.7) and `chat.tool_registry.CHAT_TOOL_SURFACE` (Unit
4.5.1), call `session.send(body.message)`, return `{"session_id":...,
"reply": ...}`. Non-streaming only in this unit — `stream()` is deferred
(Unit 4.5.9).
**Done criteria.** Via a FastAPI test client: POST a message, get a reply.
POST a follow-up to the same `session_id` (e.g. "what did I just ask you
about?") and confirm the reply demonstrates the model actually has the
prior turn's context — this is the concrete end-to-end proof that Unit
4.5.6's session persistence works through the real API layer, not just
in-process. This is also the **Phase 4.5 exit gate** referenced in
`BUILD_ORDER.md` once at least 2 structurally-distinct providers pass it.
**Dependencies.** Units 4.5.6, 4.5.7, Unit 4.1 (existing FastAPI app).

### Unit 4.5.9 — Deferred: streaming + optional Anthropic chat adapter
**Scope.** Explicitly NOT required for the Phase 4.5 exit gate — flagged
as its own unit so it's never accidentally treated as blocking, same
convention as Unit 1.8b (font matching).
**Implementation.** Streaming: implement `OpenAICompatibleProvider.
stream()` using the `openai` SDK's `stream=True` + tool-call delta
accumulation (tool call arguments arrive in fragments across chunks and
must be concatenated per `tool_call.index` before parsing as JSON) — this
is the one provider worth streaming first since OpenAI's streaming +
tool-calls interaction is the best-documented of the five. Optional
Anthropic adapter: `chat/providers/anthropic_chat.py::
AnthropicChatProvider` — not requested in the original ask but the
interface makes it a cheap add for a user who'd rather drive the built-in
chat with a Claude subscription; uses `client.messages.create(tools=
[{"name":..., "description":..., "input_schema": t.parameters_schema} for
t in tools], ...)` (note: `input_schema`, not `parameters` — a real
naming difference from the OpenAI shape, though structurally closer to
OpenAI's than Gemini's). Stub this one (`raise NotImplementedError`) until
a concrete need shows up, per the same "interface-now, implement-later"
discipline as `semantics/providers/gemini_provider.py` was for L2.
**Done criteria.** If implemented: streaming produces incremental text
chunks to the caller and still correctly assembles a complete tool call by
the end of the stream (test against a forced multi-chunk tool-call-argument
fixture, since real streaming chunk boundaries aren't guaranteed
reproducible). If deferred: no done criteria apply, this unit simply isn't
started yet — do not let it block Phase 5.
**Dependencies.** Unit 4.5.3 (streaming), Unit 4.5.2 (Anthropic adapter
shape).

---

## PHASE 5 — Library + product surface

### Unit 5.1 — Legal review gate (process, not code)
**Scope.** Before any pre-seeded template library work: get explicit
legal review of the template-library sourcing question
(`DESIGN_NOTES.md` §13, open question 4). This is a process step — there
is no code to write for this unit, but no later unit in this phase should
start before it's resolved.
**Done criteria.** A written decision (even a one-paragraph one) exists on
whether/how pre-analyzed third-party templates can be distributed, and
what the ingest/cache rights-attestation flow (from Unit 1.1b/`api/main.py`'s
enforcement point) needs to look like to support it.
**Dependencies.** None (can happen any time, but blocks 5.3).

### Unit 5.2 — Cache purge, wired to an operator path
**Scope.** Implement `ingest/cache.py::purge()` for real (it was
deferred from Unit 1.2), and expose it via an operator-only path — either
an admin CLI command or an authenticated-admin-only API endpoint.
**Implementation.** `purge()`: delete the cached normalized video, WAV,
probe JSON, trace JSON, contact sheets, and any templates whose
`source_trace_hash` matches, all under `{cache_root}/{content_hash}/` plus
any templates stored elsewhere keyed by that hash. Log the `reason` string
to an audit log (append-only file or DB table) — never log the content
itself. Wire this to `cli/analyze.py`-style admin command, e.g.
`python -m cli.admin purge <hash> --reason "..."`, or a `POST
/admin/purge` FastAPI endpoint gated by an admin auth check (reuse
`mcp/auth.py`'s token verification if hosted mode already exists, or a
simple static admin token for now if it doesn't).
**Done criteria.** Purging a known cached hash removes every artifact
under its cache directory (verify via filesystem check) and a subsequent
`analyze_video` call on the same source re-runs the full pipeline (cache
miss) rather than finding stale cached data.
**Dependencies.** Unit 1.2, Unit 5.1 (the purge path should exist before
any shared/pre-seeded library data is distributed).

### Unit 5.3 — Template library seeding
**Scope.** Populate 100+ pre-analyzed templates (spec §8.6 cold-start
requirement), sourced per Unit 5.1's resolved policy.
**Implementation.** Run the full Phase 1-3 pipeline (via `cli/analyze.py`
or the API) against a curated list of source videos matching the
sourcing policy, store the resulting templates in a dedicated library
table/index (Postgres + pgvector, per spec §10's storage choice — this is
the first unit that actually needs that stack; don't stand up Postgres
before this unit needs it), embedding each template's style summary/genre
for `search_library`'s semantic search.
**Done criteria.** >= 100 templates exist in the library store, each
retrievable and each passing basic schema validation.
**Dependencies.** Unit 5.1, Phases 1-3.

### Unit 5.4 — search_library completion
**Scope.** Finish `mcp/tools.py::search_library()` against the real
library store from Unit 5.3 (it was a stub/empty-result placeholder as of
Unit 4.4).
**Implementation.** Embed the query text (same embedding model used to
index templates in Unit 5.3), nearest-neighbor search via pgvector,
combine with any `filters` (genre, duration range, etc — plain SQL
filtering alongside the vector search).
**Done criteria.** A handful of representative queries ("high energy
product reveal," "talking head hook") return plausible top-k templates
from the seeded library.
**Dependencies.** Unit 5.3.

### Unit 5.5 — Thin web UI
**Scope.** A minimal web UI over the existing `api/main.py` endpoints —
last, deliberately, since the MCP surface is meant to be usable without
one. Full UI design is out of scope for this instructions document; when
you reach this unit, treat it as its own design pass, not something to
improvise unit-by-unit here.
**Dependencies.** All prior phases.
