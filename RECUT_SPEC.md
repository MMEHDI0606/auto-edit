# RECUT — Technical Specification v0.1

**Working title:** RECUT
**One-line:** Watch a short-form video, decompose the edit into a machine-readable recipe, and re-render that same edit with someone else's footage.
**Interface:** Local app + MCP server (usable directly from a Claude / Cursor / OpenClaw subscription) **plus a built-in, provider-agnostic conversational chat UI** (talk to RECUT directly — "make this punchier," "swap the clip in slot 3" — backed by whichever LLM the user configures; see §9A).

---

## 0. Product definition

### 0.1 What it does
Given a URL or an uploaded MP4 of a short-form video (Reels / Shorts / TikTok, 5–90s), RECUT produces:

1. An **Edit Trace** — a frame-accurate, evidence-backed description of every cut, motion, text layer, effect, and audio hit.
2. A **Template** — a parameterized version of that trace with the source footage removed and replaced by **slots**.
3. A **filled render** — the user drops clips/images in, the system assigns them to slots (or asks the human to), and renders an MP4 matching the original edit.
4. A **conversational way to do all of the above** — a built-in chat interface, backed by a provider of the user's choice, that turns natural-language requests ("make this punchier," "swap the clip in slot 3," "recreate this edit style but slower") into the same underlying operations (§9.3/§9A) that a human would otherwise drive through MCP or a UI.

### 0.2 What it explicitly does NOT do
- It does not copy the original footage.
- It does not generate new footage (no diffusion models in v1).
- It does not attempt pixel-perfect replication of proprietary effect presets. It targets **perceptual equivalence** — a viewer says "that's the same edit," not a frame-diff of zero.

### 0.3 Primary user
A creator or small agency who sees a Reel that performs well and wants to run their own footage through the same edit structure, in minutes, without reverse-engineering it by hand in CapCut.

---

## 1. System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ L0  INGEST          yt-dlp / direct upload / cache              │
├─────────────────────────────────────────────────────────────────┤
│ L1  SIGNAL          deterministic CV + DSP  →  Edit Trace       │
│                     (no LLM; measurable, reproducible)          │
├─────────────────────────────────────────────────────────────────┤
│ L2  SEMANTICS       VLM interprets evidence pack → labels,      │
│                     slot roles, style summary (gated by L1)     │
├─────────────────────────────────────────────────────────────────┤
│ L3  COMPILER        Trace + semantics → Template JSON (+ OTIO)  │
├─────────────────────────────────────────────────────────────────┤
│ L4  MATCHER         user assets → slot bindings (CLIP + rules)  │
├─────────────────────────────────────────────────────────────────┤
│ L5  RENDER          Remotion / Revideo → MP4                    │
├─────────────────────────────────────────────────────────────────┤
│ L6  MCP SERVER      exposes L0–L5 as tools/resources to agents  │
├─────────────────────────────────────────────────────────────────┤
│ L7  CONVERSATIONAL  built-in, provider-agnostic chat UI; talks  │
│     INTERFACE       to the SAME operations as L6, in-process    │
└─────────────────────────────────────────────────────────────────┘
```

**L7 is drawn beside L6, not stacked on top of it.** Both are thin
presentation layers over the same L0–L5 operations surface
(`api/workers.py` + the tool implementations in `mcp/tools.py`). L7 does
**not** act as an MCP client of RECUT's own L6 server — see §9A for why
that would be the wrong mechanism despite looking like elegant reuse.

**Core design rule:** the LLM never *measures*. Deterministic tools measure; the LLM only *labels and explains* what the tools found. Every semantic claim in the output must be traceable to a numeric signal. This one rule kills ~80% of the hallucination failure modes you would otherwise hit.

---

## 2. L0 — Ingest

### 2.1 Components
| Concern | Tool |
|---|---|
| Download | `yt-dlp` (YouTube, Shorts; IG/TikTok via extractors) |
| Normalize | `ffmpeg` — force CFR, known fps, known color space |
| Probe | `ffprobe` — duration, fps, VFR flag, rotation matrix, audio streams |
| Cache | content-hash (SHA256 of normalized video) → object store |
| Optional agent-side fetch | Agent Reach (wraps yt-dlp + platform readers, MCP-compatible) |

### 2.2 Normalization step (mandatory, do not skip)
```bash
ffmpeg -i in.mp4 -vsync cfr -r 30 -pix_fmt yuv420p \
       -vf "scale=1080:1920:force_original_aspect_ratio=decrease" \
       -c:v libx264 -crf 18 -c:a pcm_s16le norm.mp4
```
Short-form video is frequently **variable frame rate**. If you analyze VFR directly, every timestamp downstream drifts and your beat alignment silently breaks. Normalize to CFR first, store the original↔normalized time map.

### 2.3 Ingest policy
- **Supported path:** user uploads a file, or provides a URL they have rights to pull.
- Cache by hash so the same viral video is analyzed once across all users. This is the single biggest cost saver.
- Store: normalized video, extracted WAV, frame index, probe JSON.

---

## 3. L1 — Signal extraction (the Edit Trace)

This layer is pure, deterministic, testable. It runs without any model API and its output is the ground truth everything else builds on.

### 3.1 Shot boundary detection
- **PySceneDetect** with `AdaptiveDetector` + `ContentDetector` in parallel; union the results, then reconcile.
- Set `min_scene_len` to **2–3 frames**, not the default. Short-form edits routinely cut every 6–10 frames and default settings will merge them.
- Classify each boundary:
  - **Hard cut** — single-frame HSV histogram distance spike
  - **Dissolve/fade** — sustained elevated distance over 3–15 frames with monotonic blend
  - **Whip / motion transition** — boundary coincides with optical-flow magnitude spike on both sides (blur-matched)
  - **Flash / white-frame** — luminance mean spike > 2σ
  - **Zoom transition** — scale factor discontinuity in the affine model
- Output: `cuts[] = {frame, t, type, confidence, evidence{}}`

### 3.2 Camera / framing motion
Per frame pair, estimate a partial affine transform from ORB or SIFT matches:
```python
M, inliers = cv2.estimateAffinePartial2D(pts_prev, pts_next, method=cv2.RANSAC)
# decompose M -> tx, ty, scale, rotation
```
Accumulate per shot into curves:
- `zoom_curve[]` (scale, cumulative) → detects **punch-in**, **slow push**, **zoom-out reveal**
- `pan_curve[]` (tx, ty) → pans, whips
- `shake_score` = high-frequency energy of (tx, ty) after detrending → handheld / shake effect
- Dense flow (Farnebäck, or RAFT if you have GPU budget) as a fallback when feature matching fails on low-texture frames.

Fit each curve to a small library of primitives with easing (`linear`, `easeIn`, `easeOut`, `easeInOut`, `spring`) and store residual error. If residual is high, store the raw curve as a keyframe list.

### 3.3 On-screen text
1. Sample frames at 5–10 fps (not 1 fps — text often flashes for <500ms).
2. **PaddleOCR** or **EasyOCR** per sampled frame → boxes + text + confidence.
3. **Temporal grouping:** cluster boxes across frames by (normalized bbox IoU, string similarity ≥ 0.8) into a **text layer** with `t_in`, `t_out`.
4. Per layer extract:
   - normalized position + size (relative to 1080×1920 safe zones)
   - fill colour, stroke colour, stroke width (sample inside/outside glyph mask)
   - background pill / highlight box presence
   - entrance/exit animation: track bbox and alpha over the first/last 8 frames → classify `pop`, `slide_up`, `typewriter`, `fade`, `bounce`, `word_by_word`
   - font: render candidate fonts from a curated library, compare glyph raster to crop, pick nearest (see §8.6 — this is approximate by design)
5. Classify layer role: `hook_title`, `caption_burnin` (matches Whisper transcript), `lyric` (matches music, not speech), `label`, `cta`, `watermark`.

### 3.4 Audio
- **librosa**: `beat_track` → tempo + beat grid; `onset_detect` → hit points; spectral-clustering segmentation → intro/verse/drop boundaries.
- **faster-whisper** with word timestamps → speech transcript.
- Separate speech vs music energy (e.g. Demucs stem split) so lyric text and spoken captions can be told apart.
- **Cut-to-beat analysis:** for each cut, compute offset to nearest beat. Report `beat_lock_ratio` and the median offset (editors habitually cut 1–3 frames *early*; preserve that offset, don't snap to zero).

### 3.5 Effects and looks
| Effect | Detection signal |
|---|---|
| Freeze frame | frame diff ≈ 0 while audio continues |
| Speed ramp | motion magnitude discontinuity within a shot + audio pitch/tempo shift |
| RGB split / glitch | per-channel cross-correlation offset > 0 |
| Flash / strobe | luminance spikes at beat positions |
| Blur pulse | Laplacian variance dips |
| Vignette / grade | per-shot histogram stats vs neutral reference; store as a 3D-LUT approximation |
| Overlay / grain | high-freq residual after temporal median |
| Masks / cutouts | segmentation (SAM2 or rembg) if subject is isolated from background |

### 3.6 Edit Trace schema (abridged)
```jsonc
{
  "trace_version": "1.0",
  "source": { "hash": "...", "duration_s": 14.9, "fps": 30, "w": 1080, "h": 1920 },
  "audio": {
    "tempo_bpm": 128.0,
    "beat_grid_s": [0.12, 0.59, 1.06, ...],
    "sections": [{ "t_in": 0.0, "t_out": 4.2, "label": "intro" }],
    "beat_lock_ratio": 0.86,
    "median_cut_offset_frames": -2
  },
  "shots": [
    {
      "id": "s1", "t_in": 0.0, "t_out": 1.23,
      "in_transition": { "type": "cut" },
      "out_transition": { "type": "whip_pan", "duration_f": 4, "direction": "left" },
      "motion": { "primitive": "punch_in", "from_scale": 1.0, "to_scale": 1.18, "easing": "easeOut", "residual": 0.03 },
      "effects": [{ "type": "shake", "amplitude_px": 6, "freq_hz": 9 }],
      "grade": { "contrast": 1.12, "saturation": 1.25, "temp": 200 },
      "content": { "shot_type": "medium_closeup", "has_face": true, "subject_motion": "high" }
    }
  ],
  "text_layers": [
    {
      "id": "t1", "t_in": 0.2, "t_out": 2.4,
      "string": "POV: you finally",
      "role": "hook_title",
      "box": { "x": 0.5, "y": 0.22, "w": 0.8, "anchor": "center" },
      "style": { "font_guess": "Poppins-ExtraBold", "font_confidence": 0.61,
                 "fill": "#FFFFFF", "stroke": "#000000", "stroke_px": 4, "size_rel": 0.062 },
      "animation": { "in": "pop", "out": "fade", "in_duration_f": 6 }
    }
  ],
  "evidence": { "cut_detector": "adaptive+content", "ocr_fps": 8, "flow": "orb_affine" }
}
```

---

## 4. L2 — Semantic interpretation (VLM layer)

### 4.1 Input: the "evidence pack", not the raw video
Never stream the whole video into a model at high FPS — it is expensive and the model will invent effects. Instead build a compact pack:
- A **contact sheet** per shot: first / middle / last frame, tiled with burned-in timestamps.
- The numeric Edit Trace from L1 (already small).
- OCR strings + transcript + beat grid.

### 4.2 Two-pass strategy
1. **Triage pass** (cheap model, whole-video contact sheet at low res): overall structure, genre, hook type, pacing description.
2. **Deep pass** (per shot, only where L1 confidence is low or content labelling is needed): shot type, subject, what role this shot plays ("product reveal", "before state", "reaction").

### 4.3 Hard constraints on the model
- **Evidence gating:** the model may only assign an effect label from the enum of effects L1 actually flagged for that shot. If L1 found no glitch, "glitch" is not a legal output token.
- **Schema-constrained output:** JSON schema + Pydantic validation + one repair retry, then fail loudly rather than silently emitting garbage.
- **Pin model versions.** Store `model_id` in the trace. A model upgrade must not silently change existing templates.

### 4.4 Model options
- **Gemini** (native video input, configurable FPS and clipping, large context) — best for the triage pass on raw video.
- **Claude / GPT-class vision** — best for the per-shot structured deep pass on contact sheets.
- **Local option** (Qwen-VL / InternVL class) for cost control and for users who won't upload third-party video to a hosted API.

Make the model layer an interface with 3 implementations. Do not hard-couple to one vendor — this is your most volatile dependency.

---

## 5. L3 — Template compiler

### 5.1 Slotting
Each shot becomes a **slot**:
```jsonc
{
  "slot_id": "slot_01",
  "order": 1,
  "duration_s": 1.23,
  "duration_flex": { "min_s": 0.9, "max_s": 1.6, "snap": "beat" },
  "requirements": {
    "orientation": "vertical",
    "shot_type_pref": ["medium_closeup", "closeup"],
    "needs_face": true,
    "motion_pref": "high",
    "role": "hook"
  },
  "applied": {
    "motion": { "primitive": "punch_in", "to_scale": 1.18, "easing": "easeOut" },
    "grade_ref": "grade_a",
    "out_transition": "whip_pan_left_4f"
  },
  "human_instruction": "Drop a close-up of your face reacting. Must have visible motion. ~1.2s."
}
```
The `human_instruction` field is the product. That string is what the user actually reads.

### 5.2 Audio handling in the template
Audio is stored as a **reference, not as a file**:
```jsonc
"audio_ref": {
  "platform": "instagram",
  "track_title": "...",
  "artist": "...",
  "start_offset_s": 12.4,
  "beat_grid_s": [...],
  "embed_permitted": false
}
```
Rationale in §8.1. The renderer can output a **silent-but-beat-locked** cut that the user finishes inside Instagram/CapCut with the licensed track, or mux audio the user supplies.

### 5.3 Interchange formats
Export the template three ways:
1. **RECUT JSON** — native, lossless.
2. **OpenTimelineIO (.otio)** — opens in Resolve / Premiere workflows. This is your credibility feature for pro users.
3. **Remotion props JSON** — direct render input.

Version the schema from day one (`trace_version`, `template_version`) with a migration path. You will change this schema a dozen times.

---

## 6. L4 — Asset matcher

Given user assets and a template:
1. Probe each asset (duration, orientation, fps).
2. Run per-asset: face detection, shot-type classification, motion score, CLIP embedding, optional Whisper if it has speech.
3. Score every (asset, slot) pair against `requirements`. Solve the assignment with the Hungarian algorithm under the constraint that each asset is used ≤ N times.
4. Auto-select the in-point within each asset: pick the sub-window with the highest motion/quality score of the required duration, then snap the cut to the beat grid with the preserved `median_cut_offset_frames`.
5. Return bindings **with confidence**, and always let the human override. Never silently misplace a clip — surface "I put your kitchen clip in slot 3; you may want your face there instead."

---

## 7. L5 — Renderer

### 7.1 Engine choice
| Engine | Notes |
|---|---|
| **Remotion** | React-based, mature, great text animation, deterministic. **Check licensing: Remotion is free for individuals/small teams but requires a paid company licence above a headcount threshold — verify before commercialising.** |
| **Revideo** | Open-source, Motion Canvas–based, built specifically for programmatic video templates in TypeScript. Lighter licence risk; smaller ecosystem. |
| **ffmpeg + filtergraph** | Fallback for simple cut-only templates; fastest; poor for kinetic text. |

Recommendation: build the renderer behind an interface, start on **Revideo** for licence cleanliness, keep a Remotion adapter.

### 7.2 Effect library
Hand-build a library of primitives that map 1:1 to L1's detected primitives: `punch_in`, `slow_push`, `whip_pan`, `shake`, `flash`, `rgb_split`, `freeze`, `speed_ramp`, `text_pop`, `text_typewriter`, `text_word_by_word`, `caption_karaoke`. Each takes the numeric parameters from the trace. If L1 detects something with no library primitive, degrade gracefully to the nearest match and flag it in the render report.

### 7.3 Output
- MP4 (H.264, 1080×1920, CRF 20), plus a **render report** listing every approximation made.
- Optional: still storyboard PNG and a 2s GIF preview for fast iteration without a full render.

---

## 8. Risks, failure modes and blockers

Ordered by how likely they are to actually stop you.

### 8.1 Legal / rights (the real blocker)
- Your point stands: the *creator* doesn't own the song or the lyrics, so they can't stop you reusing that structure. **But the publisher does own the lyrics**, and public display/synchronisation of lyric text is a licensed act. When a creator uses a track from Instagram's music library inside Instagram, that use is covered by **Meta's licence deals — and that coverage does not travel with an MP4 rendered by your app.**
  - **Mitigation (architectural, do this):** never mux a commercial track into your render. Store the track as a reference + beat grid, render silent or with user-supplied audio, and have the user attach the licensed track inside Instagram/CapCut where the licence exists. Same treatment for lyric text layers: reproduce the *layer* (timing/position/style) and let the user type or confirm the words.
- **Scraping vs Terms of Service** is a separate and more immediate problem than copyright. Automated collection from Instagram violates its ToS regardless of who owns the music. Design the product around **user-provided files and user-authorised pulls**, keep bulk crawling out of the hosted service, and get an actual lawyer to review before you launch paid.
- **Editing style itself is not protectable** in most jurisdictions — structure, pacing, and technique are the free part. That's the part your product sells. Lean into it explicitly in your marketing; it's your legal high ground.

### 8.2 Ingest fragility
- yt-dlp extractors break weekly; IG increasingly requires an authenticated session; TikTok blocks datacentre IPs.
- **Mitigations:** treat downloading as optional and best-effort, make upload the first-class path, pin + auto-update yt-dlp, cache aggressively by hash, never let an ingest failure kill a job that could run on an uploaded file.

### 8.3 Analysis accuracy — the specific things that will break
| Failure | Why | Mitigation |
|---|---|---|
| Missed rapid cuts | default `min_scene_len` merges 4-frame shots | set to 2–3 frames; validate on a hand-labelled set |
| Whip transition read as a cut | motion blur destroys features | require both-side flow spike before labelling; else default to cut |
| Speed ramps unrecoverable | information is genuinely destroyed | approximate with 2–3 linear segments; flag low confidence |
| Kinetic typography | per-character animation is very hard to invert | support a fixed set of common animations; approximate the rest, expose them as editable |
| Font identification | no reliable open model exists | curated library + raster nearest-neighbour; always show top-3 and let the user pick |
| Platform watermarks | TikTok/IG bugs pollute OCR + optical flow | detect and mask static corner regions before OCR/flow |
| Compression artifacts | re-encoded uploads wreck subtle grade/grain estimates | operate on the highest available bitrate; mark grade estimates as low confidence |
| VFR timestamp drift | phone-captured source | mandatory CFR normalisation (§2.2) |
| Burned-in captions vs speech | look identical to OCR | cross-match OCR strings against Whisper transcript to classify |
| VLM invents effects | models are agreeable | evidence gating (§4.3) |

### 8.4 Fidelity gap
CapCut/Instagram presets have proprietary easing curves and looks. You will land at "recognisably the same edit," not "identical." **Set this expectation in the product copy.** Ship the render report so the user knows exactly what was approximated and can fix it in 30 seconds rather than wondering why it feels off.

### 8.5 Cost and latency
- A 20s video at 8fps OCR = ~160 OCR passes + ~600 flow estimates + a VLM pass. Expect **30–120s per video** on CPU, much less with GPU.
- Cost control: hash-cache everything; run L1 before L2 and skip L2 entirely for cut-only templates; use the cheap model for triage; store traces so re-rendering never re-analyses.

### 8.6 Product/business blockers
- **Cold start:** one template is not a product. You need a seeded library of 100+ pre-analysed popular templates before launch.
- **Platform dependence:** if Instagram ships a native "remix this edit" feature, your wedge narrows. Defend by being cross-platform and by owning the **template library + matcher quality**, not the analysis alone.
- **GPU cost at scale** if you go hosted; consider local-first (which also sidesteps some of §8.1 and §8.2).
- **Licence audit** of every dependency (Remotion especially) before you charge money.

---

## 9. L6 — MCP server

### 9.1 Why MCP matters here
It makes RECUT usable from any agent the user already pays for — a Claude, Cursor, or OpenClaw subscription becomes the front end, and you don't build a UI on day one. The agent does the conversational part ("which clip goes in slot 3?") for free.

### 9.2 Two deployment modes
| Mode | Transport | Auth | For |
|---|---|---|---|
| **Local** | stdio | none | power users; keeps video on-device; no upload concerns |
| **Hosted** | Streamable HTTP | OAuth 2.1 | subscription users adding RECUT as a remote connector |

### 9.3 Tool surface
```
recut.analyze_video(source: url|file_path|upload_id, depth: "fast"|"full")
    → { job_id }                      # async; analysis exceeds MCP call timeouts

recut.get_job(job_id)
    → { status, progress, stage, error?, result_refs? }

recut.get_trace(job_id, sections?: ["shots","text","audio"])
    → Edit Trace (paginated — a full trace can exceed context)

recut.get_template(job_id, format: "recut"|"otio"|"remotion")
    → { template_id, template }

recut.describe_template(template_id)
    → human-readable breakdown + per-slot instructions   # the "read the edit" feature

recut.list_slots(template_id)
    → [{ slot_id, duration_s, human_instruction, requirements }]

recut.register_assets(files[])            → asset_ids
recut.match_assets(template_id, asset_ids) → proposed bindings + confidences
recut.bind(template_id, { slot_id: asset_id }) → binding_id

recut.adjust_template(template_id, changes: {
    global_duration_scale?: float,       # e.g. 1.25 = 25% slower overall
    energy_bias?: "punchier"|"calmer",   # biases slot durations toward
                                          # duration_flex.min_s/max_s and
                                          # motion_pref, does not invent
                                          # new motion/effects
    slot_overrides?: { slot_id: {...} }
}) → { new_template_id }
    # Added for §9A (chat) but equally usable from any MCP client. Produces
    # a NEW template (Template.derived_from = source template_id); never
    # mutates a template in place. `changes` is a small fixed vocabulary,
    # not free-form — this is the L3-layer analogue of the evidence-gating
    # rule: the caller (human, MCP agent, or the L7 chat model) picks a
    # knob from a constrained, validated schema; RECUT's own deterministic
    # template math (reusing compiler/beat_snap.py) computes the actual new
    # duration_s/duration_flex values. The caller never emits a raw number
    # for an individual shot's timing "from vibes."

recut.preview(binding_id)   → storyboard PNG / short GIF
recut.render(binding_id, opts:{ include_audio:bool, resolution })
    → { job_id }
recut.get_render(job_id)    → { url, render_report }

recut.search_library(query, filters) → templates from the seeded library
```

**Resources:** `recut://trace/{id}`, `recut://template/{id}`, `recut://render/{id}`
**Prompts:** `recreate_this_edit`, `explain_this_edit`, `find_similar_template`

### 9.4 MCP design rules learned the hard way
- **Everything long-running is async.** Analysis takes 30–120s; MCP clients time out. Return `job_id` immediately, poll via `get_job`.
- **Never return a full trace by default.** A 60s video trace can be tens of thousands of tokens. Return a summary + a resource URI, and let the agent request sections.
- **Return files as artifacts/URIs, not base64 blobs.** Video in context is a fast way to blow a session.
- **Tool descriptions are prompt engineering.** Write them for a model, with explicit "call this after that" ordering hints.
- **Idempotency keys** on render calls — agents retry.
- Treat any text extracted from a third-party video (OCR, captions) as **untrusted input**. It can contain prompt injection. Wrap it and say so in the tool description.

### 9.5 Optional: agent memory layer
**TencentDB-Agent-Memory** (MIT, TypeScript, built as an OpenClaw plugin) is a reasonable fit for a v2 concern: it does symbolic compression of heavy tool logs plus layered long-term memory, which maps well onto "remember this creator's recurring edit patterns across sessions" and onto keeping analysis logs out of the context window. Caveat: it's built around the OpenClaw plugin model, so using it elsewhere means writing an adapter. Don't take this dependency in v1 — a plain Postgres + pgvector table of past traces gets you 90% of the benefit with 5% of the integration cost.

---

## 9A. L7 — Conversational interface

### 9A.1 What it is and why it's separate from §9
§9's MCP server makes RECUT usable from an agent the user *already* pays for
(Claude Code, Cursor, an OpenClaw-based assistant) — that agent supplies its
own LLM and does the conversational part for free. This section adds the
opposite case: a **first-class, built-in chat UI**, shipped as part of the
RECUT product itself, backed by an LLM the user configures directly (their
own OpenAI/NIM/OpenRouter/vLLM/Gemini key or endpoint) — for the user who
doesn't have, or doesn't want to route through, an external agent
subscription. This is additive, not a replacement for §9; both ship.

### 9A.2 Where it sits
L7 is a **sibling of L6**, not a layer built on top of it (see §1's
diagram). Both L6 and L7 are thin presentation wrappers over the same
underlying operations (`api/workers.py` job functions, exposed as plain
Python callables in `mcp/tools.py`). Concretely: **L7 does not act as an MCP
client of RECUT's own L6 server.** That would look like elegant reuse (same
tool surface, "just point the chat model's tool-calling loop at your own
MCP endpoint") but the isolation MCP's transport buys — a stable wire
protocol between two processes that don't already trust each other — is
irrelevant here, because L7's chat backend and L6's tool implementations run
in the same deployment and the same trust boundary. Going through a stdio
subprocess or an HTTP loopback to reach your own in-process functions adds
serialization/process overhead and a second place tool-call semantics can
drift, for zero actual isolation benefit. Instead, L7 imports the tool
functions directly (`from mcp.tools import list_slots, match_assets, bind,
render, ...`) and reuses their **docstrings and parameter shapes** as its
own tool specs, so the tool surface and its documentation are defined once
and consumed by both L6's MCP registration and L7's tool-calling loop.

**This split is exact and one-directional, stated explicitly:** L7's own
conversational interface (the thing a human types natural language into)
is reachable **only** via its dedicated API (§9A's chat endpoint,
`INSTRUCTIONS.md` Unit 4.5.8 — `POST /chat/{session_id}/message`). It is
**not** registered as an MCP tool or resource — there is no
`recut.chat(...)` tool, no "chat_with_recut" MCP entry, nothing an
external MCP client (Claude Code, Cursor, OpenClaw) can call to drive a
conversation through RECUT's own L7. An external agent that wants
conversational access to RECUT supplies its own LLM and talks through §9's
existing MCP tool surface, same as today — that's what §9's tools are for.
Conversely, everything that isn't L7's chat endpoint — `analyze_video`,
`get_template`, `match_assets`, `bind`, `render`, `adjust_template`, all of
it — stays MCP-only, exactly as originally designed; L7's existence is not
license for any other RECUT capability to grow a second, non-MCP API
surface. The only new API surface this feature introduces is the one chat
endpoint itself.

### 9A.3 Tool-calling surface
L7 exposes the LLM the same operations set as §9.3, unchanged, plus
`adjust_template` (§9.3, added specifically because "make this punchier" /
"recreate this edit style but slower" have no lever to pull without a
template-mutation tool — every other example request in this section maps
onto an existing tool: "swap the clip in slot 3" → `bind`). One
model-facing parameter is deliberately hidden from the tool schema:
`render`'s `idempotency_key` is generated by the tool-calling loop itself
(a fresh UUID per call), never something the chat model is asked to invent
— a human casually chatting is not going to supply a sensible idempotency
key, and letting the model omit or hallucinate one would defeat its purpose
(§9.4).

### 9A.4 Multi-provider LLM abstraction
The user must be able to point RECUT's chat at OpenAI, NVIDIA NIM,
self-hosted vLLM, Google Gemini, or OpenRouter — "effectively all of them."
This is **not** the same interface as §4.4/§4's `SemanticProvider` (the L2
model abstraction). The two are different shapes of task on a different
volatility axis:

| | L2 `SemanticProvider` (§4.4) | L7 chat provider |
|---|---|---|
| Call shape | single-shot: evidence pack in, one schema-validated JSON object out | multi-turn: message history + tool definitions in, either a tool call or final text out, looped until done |
| What varies | which vision model best does evidence-gated shot labeling | which LLM subscription/self-hosted endpoint the *user* already has |
| Native SDK shape | one structured-output call per pass | streaming-capable chat-completions with function/tool calling |

Reusing `SemanticProvider`'s two fixed methods (`triage`, `deep_pass`) for
a conversational tool-calling loop would force one of the two use cases to
distort its natural shape. L7 gets its **own** interface,
`chat.providers.base.ChatProvider`, structurally parallel to
`SemanticProvider` (an ABC, pinned `model_id`, "define the interface fully,
implement adapters as concrete need arises") but with a method shaped for
multi-turn tool-calling instead of single-shot structured extraction.

**Provider adapters — shim vs. real adapter:**
- **OpenAI, NVIDIA NIM, OpenRouter, self-hosted vLLM** — all four serve (or
  can serve) an **OpenAI-compatible** `chat.completions.create(...,
  tools=[...])` endpoint. One `OpenAICompatibleProvider` base class,
  parameterized by `base_url`/`api_key`/`model_id`/extra headers, covers all
  four; the concrete classes are thin subclasses supplying config only. NIM
  and OpenRouter's OpenAI-compatibility is a genuine one-shim-covers-many
  case. vLLM is the same wire shape but the *actual* tool-calling behavior
  depends on the served model's chat template and vLLM being launched with
  the right `--tool-call-parser` — this is a real operational caveat, not
  free, even though the code path is shared.
- **Google Gemini** — genuinely different function-calling shape: separate
  `system_instruction` (not a "system" role message), `user`/`model` roles
  (not `user`/`assistant`), tool results sent back as a `function_response`
  **`user`-role** part (not a `tool`-role message), function-call arguments
  arrive already parsed as a dict (not a JSON string to `json.loads`), and
  a single turn can contain multiple `function_call` parts with no
  provider-issued call id. This needs a real, hand-written adapter.

See `DESIGN_NOTES.md` for the full rationale and `INSTRUCTIONS.md` Phase
4.5 for exact adapter implementations (library calls, request/response
shapes).

### 9A.5 Session handling and untrusted text
Conversation history is session-scoped and persisted (reusing the Redis
job-store infrastructure already built for §9.4's async job pattern, keyed
by `session_id`, TTL'd) so a session survives across HTTP requests, not just
in-process. Any OCR/transcript/caption string that a tool result surfaces
into the conversation (e.g. `describe_template`'s output, or a `get_trace`
call the model makes) **must** be passed through the same
`wrap_untrusted_text()` used by §9.4's MCP tools before it re-enters the
model's context — arguably higher-stakes here than the external-agent MCP
case, since the "agent" the untrusted text is being smuggled toward is a
first-party chat model the end user is casually trusting in real time.

---

## 10. Tech stack

| Layer | Choice |
|---|---|
| Orchestration | Python 3.11, FastAPI, Celery/RQ + Redis |
| CV | OpenCV, PySceneDetect, PaddleOCR, SAM2 (optional), CLIP |
| Audio | librosa, faster-whisper, Demucs |
| Media | ffmpeg / ffprobe, yt-dlp |
| Models | pluggable: Gemini (video triage), Claude/GPT (structured deep pass), local VLM option |
| Storage | Postgres (metadata, traces) + pgvector (template/asset embeddings) + S3/R2 (media) |
| Render | Revideo (primary) / Remotion (adapter), Node worker |
| Interchange | OpenTimelineIO |
| MCP | official Python or TS MCP SDK; stdio + streamable HTTP |
| Chat (L7) | `openai` Python SDK (covers OpenAI, NVIDIA NIM, OpenRouter, vLLM via `base_url` override) + `google-genai` SDK (Gemini); session store reuses Redis (same as the §9.4 job store) |

---

## 11. Build order

**Phase 1 — Prove the analysis (3–4 weeks).**
CLI only. Ingest → cuts + beats + text layers → print an Edit Trace JSON. No LLM, no renderer. Success = hand-label 20 Reels and hit **≥90% cut-boundary F1 within ±2 frames** and **≥85% text-layer timing IoU**.

**Phase 2 — Template + render (3–4 weeks).**
Trace → Template → Revideo render with manually assigned clips. Success = 5 blind viewers rate the re-creation ≥4/5 for "same edit" on 10 templates.

**Phase 3 — Semantics + matcher (3 weeks).**
Add the VLM layer with evidence gating; add CLIP-based auto-matching; add `human_instruction` generation.

**Phase 4 — MCP server (2 weeks).**
Local stdio first, hosted HTTP + OAuth second.

**Phase 5 — Library + product surface.**
Seed 100+ templates, add search, ship a thin web UI over the same API.

---

## 12. Evaluation

Build this in Phase 1, not later. Without it you cannot tell whether a change improved anything.

- **Golden set:** 30 hand-annotated short-form videos across genres (talking head, product, dance/trend, text-heavy tutorial, cinematic b-roll).
- **Metrics:**
  - cut boundary precision/recall @ ±2 frames
  - transition-type classification accuracy
  - text layer timing IoU + string accuracy (CER)
  - beat-lock offset error (frames)
  - motion primitive classification accuracy
  - end-to-end human A/B: "same edit?" 1–5 Likert, blind
- **Regression gate:** no model or dependency upgrade merges without the golden set re-run.

---

## 13. Repo layout

```
recut/
├── ingest/          yt-dlp wrapper, normalisation, cache
├── signal/          cuts.py motion.py text.py audio.py effects.py
├── semantics/       evidence_pack.py providers/ schemas.py gating.py
├── compiler/        template.py slots.py otio_export.py
├── matcher/         probe.py score.py assign.py
├── render/          revideo/ remotion/ effects_library/
├── mcp/             server.py tools.py auth.py
├── chat/            providers/ (base.py, openai_compatible.py, gemini.py,
│                    factory.py) schemas.py tool_registry.py loop.py
│                    session.py                         # L7, see sec 9A
├── eval/            golden/ metrics.py run.py
├── schemas/         trace.v1.json template.v1.json
└── api/             FastAPI + workers
```

---

## 14. Open questions to resolve before Phase 2

1. Local-first or hosted-first? (Local sidesteps most of §8.1–8.2; hosted is a better business.)
2. Renderer licence decision — Revideo vs paid Remotion company licence.
3. How much of the grade/LUT do you attempt to recover in v1? (Recommendation: v1 stores grade stats but does not apply them.)
4. Does the template library ship pre-analysed templates, or only user-analysed ones? (Cold start says pre-analysed; legal review says be careful how you distribute them.)
5. What's the fallback UX when analysis confidence is low — refuse, or ship a partial template with flagged sections? (Recommendation: partial + flags. Refusing feels broken.)
