# RECUT — Build Order

> **This file is the phase-level map. For execution — exact scope, algorithm,
> library calls/parameters, and done-criteria for each individual unit of
> work within a phase — see `INSTRUCTIONS.md`.** Build strictly one unit at
> a time, in the order `INSTRUCTIONS.md` lays out; do not start a new unit
> until the previous one's done-criteria are met. This file's phase gates
> remain the higher-level checkpoints; `INSTRUCTIONS.md`'s per-unit done
> criteria are the granular steps that get you there.

This supersedes `RECUT_SPEC.md` §11 for sequencing purposes (the phase
*content* is mostly the same; the sequencing and gates below reflect the
judgment calls in `DESIGN_NOTES.md`). Each phase has a hard "done"
criterion — do not move on until it's met. If a phase's criterion can't be
met, that's signal to stop and reconsider the approach, not to lower the
bar and continue.

---

## Phase 0 — Contracts & scaffolding sanity (2–4 days)

Not in the original spec's build order at all — added because every
downstream phase depends on the Edit Trace / Template schemas, and
discovering a schema problem after Phase 1's analysis code is written is
expensive. This phase is mostly already done by this scaffold; verify it,
don't skip verifying it.

Tasks:
- [ ] Confirm `schemas/models.py` covers every field actually needed —
  walk through `RECUT_SPEC.md` §3.6 and §5.1/5.2 field by field and check
  it against `EditTrace`/`Template`. Add anything missing now, before code
  depends on the current shape.
- [ ] Pin real dependency versions in `pyproject.toml` (currently
  unpinned placeholders). Specifically pin `yt-dlp` (breaks weekly, spec
  §8.2) and record the pinned version somewhere `ingest/downloader.py` can
  read it into `EvidenceMeta`.
- [ ] `pip install -e ".[dev]"`, `pytest -q` passes (currently 3 tests in
  `tests/test_schemas.py` — keep these green as you extend the models).
- [ ] `python schemas/generate_json_schema.py` runs clean and the diff is
  reviewed before every commit that touches `schemas/models.py`.
- [ ] Stand up `eval/golden/` directory convention (empty is fine) and
  write down in `eval/golden/.gitkeep` — already done — the annotation
  format for the first golden video, even before any video is annotated.

**Done when:** schema models pass round-trip tests, dependencies are
pinned, and a fresh clone can `pip install` + `pytest` with no changes.

---

## Phase 1 — Prove the analysis (3–4 weeks)

Matches spec §11 Phase 1 in spirit and success criteria. CLI only. No LLM,
no renderer. Build order *within* the phase, in this order (each one
unblocks the eval harness a bit more):

1. `ingest/normalize.py` + `ingest/probe.py` — get a normalized CFR video
   + WAV out of an uploaded file. Upload path only; skip
   `ingest/downloader.py` (yt-dlp) until this works, per the "upload is
   first-class, download is best-effort" policy in `DESIGN_NOTES.md`.
2. `signals/cuts.py` — shot boundaries + transition classification. This
   is the highest-leverage module: tune `min_scene_len_frames` against a
   handful of real short-form videos before anything else.
3. `signals/audio.py` — beat grid + cut-to-beat offset. Needed for (2)'s
   output to be checkable at all (beat_lock_ratio is one of the Phase 1
   gates).
4. `signals/motion.py` — camera motion curves.
5. `signals/text.py` — OCR + temporal grouping (style extraction /
   font-matching can lag; timing + string accuracy are the graded metrics).
6. `signals/effects.py` — implement freeze/speed-ramp/rgb-split/flash/
   blur-pulse; skip `mask_cutout` (SAM2/rembg) entirely in this phase, it's
   explicitly optional (spec §3.5, `DESIGN_NOTES.md` scope trims).
7. `signals/trace_builder.py` — wire the above into one `EditTrace`.
8. `cli/analyze.py` — `python -m cli.analyze <file> --out trace.json`
   working end to end.
9. `eval/metrics.py` + `eval/run.py` + hand-annotate the first 10-15
   golden videos — do this *alongside* 2-7, not after. You cannot tell if
   tuning `min_scene_len_frames` helped without this running.
10. Write fast unit tests in `tests/signals/` against `eval/fixtures.py`
    synthetic cases as each module lands — don't wait until the module is
    "done" to add tests.

**Done when:** golden-set run over ≥20 hand-labeled videos hits ≥90% cut-
boundary F1 within ±2 frames AND ≥85% text-layer timing IoU (spec §11
Phase 1 gate, unchanged). `eval/run.py` is wired as a CI gate before Phase
2 starts.

---

## Phase 2 — Template + render, ffmpeg-first (3–4 weeks)

Deviates from spec §11 Phase 2 in one concrete way: build
`render/engines/ffmpeg_engine.py` **before** `RemotionEngine`, as a smoke
test. It has no Node dependency, so it proves the Template →
render-report pipeline shape works before paying the cost of standing up
a Node worker. Kinetic text will be visibly wrong on the ffmpeg engine —
that's expected and fine, the point is proving the pipeline plumbing, not
final render quality yet.

1. `compiler/slots.py` + `compiler/beat_snap.py` + `compiler/template.py`
   — Trace → Template, L1-only (no semantics yet, mechanical
   `human_instruction` generation).
2. `render/interface.py` + `render/engines/ffmpeg_engine.py` — cut-only
   render, manually assigned clips (no matcher yet — hand-write a
   `BindingSet` for the smoke test).
3. `render/engines/remotion_engine.py` + `render/effects_library/
   primitives.py` — the real kinetic-text-capable path. This is the bulk
   of Phase 2's effort.
4. Blind-viewer eval per spec §11 Phase 2 gate.

**Done when:** 5 blind viewers rate the re-creation ≥4/5 for "same edit"
on 10 templates, rendered via `RemotionEngine` (spec §11 gate, unchanged).
Log the `render_report` / `Template.confidence_flags` shown to viewers
alongside the scores — you want to know *which* approximations correlate
with low scores, not just the aggregate number.

---

## Phase 3 — Semantics + matcher (3 weeks)

1. `semantics/gating.py` — build the evidence gate FIRST, before any
   provider call exists, and unit-test it against synthetic
   `SemanticShotAnnotation` payloads that intentionally violate the
   allowlist. If this module is solid before a real model is ever called,
   the "VLM invents effects" failure mode (spec §8.3) is caught by tests,
   not by production incidents.
2. `semantics/providers/anthropic_provider.py` — the one concrete provider
   implementation for this phase (see `DESIGN_NOTES.md` §5). Do not start
   `gemini_provider.py` or `local_provider.py` unless a concrete need
   shows up (cost comparison, privacy requirement).
3. `semantics/evidence_pack.py` — contact sheets + evidence pack assembly.
4. Wire `semantics` output into `compiler/slots.py`'s richer
   `human_instruction` path.
5. `matcher/probe.py` → `matcher/score.py` → `matcher/assign.py`, in that
   order. Tune `SCORE_WEIGHTS` against blind-viewer or held-out human
   ratings, not intuition alone.
6. Re-run the Phase 2 blind-viewer eval with auto-matched assets instead
   of hand-assigned ones — this is a meaningfully different test
   (matcher quality, not just render quality) and deserves its own score.

**Done when:** evidence gating has unit tests covering at least one
rejection case per `EffectType`/`TransitionType`; the matcher's
auto-assigned blind-viewer score is within a small, explicitly-chosen
margin of Phase 2's hand-assigned score (pick the margin before you have
the number, so you're not rationalizing after the fact).

---

## Phase 4 — MCP server (2 weeks)

Sequencing unchanged from spec §11: stdio first, hosted HTTP+OAuth
second — but treat them as two sub-phases with separate "done" bars, not
one two-week block.

### 4a — Local stdio (no auth)
1. `mcp/tools.py` — implement the tool surface as thin wrappers over
   `api/workers.py` job functions (async job_id pattern, spec §9.4).
   `wrap_untrusted_text()` must be used everywhere OCR/transcript strings
   leave this module — check every tool's return path, not just
   `get_trace`.
2. `mcp/resources.py` — `recut://trace/{id}` etc, plus the three prompts.
3. `mcp/server.py::run_stdio_server`.
4. Manually test from an actual MCP client (Claude Code / Claude Desktop
   / Cursor) — a tool description that reads fine to a human can still be
   ambiguous to a model; this is the cheapest phase to actually dogfood.

**Done when:** a real MCP client can drive `analyze_video` →
`get_template` → `register_assets` → `match_assets` → `bind` → `render` →
`get_render` end to end without the operator touching a CLI.

### 4b — Hosted HTTP + OAuth 2.1
1. `mcp/auth.py`.
2. `mcp/server.py::run_http_server`.

**Done when:** the same tool surface works over Streamable HTTP with a
real OAuth flow, gated behind whatever hosting decision has been made by
this point (see `DESIGN_NOTES.md` §13, open question 1 — local-first is
the default, hosted mode is additive, not a replacement).

---

## Phase 5 — Library + product surface

1. **Legal review gate, before anything else in this phase**: decide
   template library sourcing per `DESIGN_NOTES.md` §13 open question 4.
   Default assumption in this scaffold is user-analyzed-only; only start
   seeding pre-analyzed third-party templates after this is explicitly
   revisited with real legal input.
2. `ingest/cache.py::purge()` — wire to an operator-accessible admin path
   (CLI flag or authenticated endpoint) if it isn't already. Do not launch
   a shared cache without this being reachable by a human who isn't you.
3. Seed 100+ templates (spec §8.6 cold-start requirement) — only after
   (1).
4. `mcp/tools.py::search_library`.
5. Thin web UI over the existing API (`api/main.py`) — last, since the
   MCP surface is meant to be usable without one.

**Done when:** cold-start problem (spec §8.6) is addressed with a
library whose sourcing has passed the legal gate in step 1, and the
takedown path in step 2 has been exercised at least once (even as a dry
run) before real user data flows through the cache.

---

## Cross-cutting: what "regression gate" means in practice

From Phase 1 onward, `eval/run.py` must be re-run — and its output
compared against the last committed baseline — before merging any change
to: `signals/*`, dependency versions (`pyproject.toml`), or any pinned
`model_id` in `semantics/providers/*`. This is not a suggestion; treat a
metric regression the same as a failing test. The golden set is the only
thing standing between "we improved something" and "we have no idea if
we improved anything," which is the exact failure mode spec §12 opens
with.
