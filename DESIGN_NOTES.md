# RECUT — Design Notes (scaffold v0.1 → v0.2 deviations)

This document explains **why the scaffold is shaped the way it is**, and
where it deliberately deviates from `RECUT_SPEC.md` (v0.1, the original
spec). Read it before implementing any module — several files reference
decisions recorded here instead of re-explaining themselves inline. If you
disagree with a decision below and want to revert to the original spec's
approach, that's fine, but change this document too so the next person
doesn't have to reverse-engineer which version is current.

The full critique this is based on is in the PR/conversation that produced
this scaffold; this document only records the decisions that actually
changed the shape of the code, not every point of agreement.

---

## 1. Naming collision: `signal/` → `signals/`

**This is a real bug, not a style choice.** The spec's own repo layout
(§13) names a top-level package `signal/`. Python has a stdlib module
called `signal` (POSIX signal handling — `SIGINT`, `SIGTERM`, etc). Any
top-level package named `signal` shadows it for every absolute import in
the process, including inside third-party dependencies. Concretely: with
a `signal/` package present, `import anyio` (a transitive dependency of
`fastapi`, and of `pytest`'s own plugin loader) breaks immediately with
`ImportError: cannot import name 'Signals' from 'signal'`. This was caught
by actually running `pytest` against the scaffold, not just review — it's
the kind of thing that looks fine until the first `pip install` pulls in
anything that touches `asyncio`/`anyio`.

**Fix:** the package is `signals/` throughout this scaffold. Update
`RECUT_SPEC.md`'s own repo layout mentally when reading it — this scaffold
is the one to follow for module boundaries, not §13's tree.

---

## 2. Schema strategy: Pydantic is canonical, JSON Schema is generated

The spec's §13 layout lists `schemas/trace.v1.json` and
`schemas/template.v1.json` as if they're hand-maintained, and separately
implies Pydantic validation exists somewhere in `semantics/`. Maintaining
both by hand desyncs within days of real development — someone adds a
field to the Pydantic model and forgets the JSON Schema, or vice versa.

**Fix:** `schemas/models.py` is the single source of truth (Pydantic v2).
`schemas/trace.v1.schema.json` and `schemas/template.v1.schema.json` are
generated artifacts, produced by `schemas/generate_json_schema.py`, and are
committed to the repo (so non-Python consumers — the Remotion/Node render
worker, OTIO tooling, MCP clients doing local validation — have something
to point a validator at without a Python runtime). **Never hand-edit the
`.schema.json` files.** Regenerate them after any model change and commit
both.

Every model that encodes a measured claim (from L1) carries a
`confidence` field where relevant; every model that encodes an LLM claim
(L2) is validated against L1-derived evidence before it's allowed to exist
(see §4 below, and `semantics/gating.py`). This is the schema-level
enforcement of the spec's central rule ("the LLM never measures") — it's
not just a review checklist, the types make the wrong thing awkward to
construct.

---

## 3. Architecture: the pipeline is not strictly linear

The spec's §1 diagram draws L0→L1→L2→L3→L4→L5→L6 as a straight pipe. In
practice L2 (semantics) needs to *request more evidence* from L1 for a
specific shot when confidence is low (§4.2's "deep pass... only where L1
confidence is low" already implies this, the diagram just doesn't show
it). Treat `signals/` as a library L2 can call into for a targeted
re-extraction (e.g., re-run `signals.text.font_match` with a larger font
candidate set for one shot), not a one-shot batch step that L2 only ever
consumes the output of. Don't build this feedback path speculatively in
Phase 1 — just don't architect `signals/` functions as batch-only in a way
that forecloses per-shot re-invocation later (this is why `signals/`
exposes per-shot functions like `extract_shot_motion`, not only
whole-video batch entry points).

---

## 4. Renderer choice: Remotion is primary, not Revideo

The spec (§7.1) recommends Revideo as primary "for licence cleanliness,"
keeping a Remotion adapter. **This scaffold disagrees and defaults to
Remotion as primary** (`common/config.py:Settings.primary_render_engine =
"remotion"`, `render/engines/remotion_engine.py` is the fleshed-out stub,
`revideo_engine.py` is the deliberately thinner one).

Reasoning: the spec itself identifies kinetic typography (per-character
text animation) as one of the two or three hardest, highest-value problems
in the whole system (§3.3, §8.3, §8.6 all return to it). Remotion has a
dramatically more mature ecosystem and community precedent for exactly
that problem — programmatic kinetic text in React — than Revideo, which is
younger, smaller, and Motion Canvas–based. Picking the less mature renderer
for the exact capability that's hardest to get right is optimizing for a
cost (the license) that is bounded, known in advance, and only triggered
by success (paid company license required above a headcount threshold —
i.e., it bites exactly when the business can afford it). The license risk
is real but it's a *business* decision with a dollar figure attached, not
an architectural one; the rendering-quality risk is open-ended and harder
to walk back once templates are built against a specific engine's
capabilities.

The `render/interface.py` abstraction (not present as a distinct file in
the original §13 tree — it only listed sibling directories with no
explicit interface module) exists so this choice is cheap to reverse:
every engine is a `RenderEngine` implementation, selected by one config
value. If Remotion's license cost becomes a real constraint before
Revideo has matured, flipping `primary_render_engine` is a one-line change,
not a rewrite. Revisit this decision explicitly before charging money —
it's also open question #2 in the original spec's §14, and this scaffold's
answer is "Remotion now, revisit at the business-model stage," not
"decide later with no default."

---

## 5. Interface-now, implement-later (providers, render engines)

The spec asks for 3 model providers (§4.4) and effectively 2-3 render
engines (§7.1) as interfaces "from day one." Agreed on the interface part;
disagreed on implementing all of them immediately — that's exactly the
kind of abstraction spend a project with zero shipped functionality can't
afford yet.

**Fix applied throughout `semantics/providers/` and `render/engines/`:**
the abstract base (`SemanticProvider`, `RenderEngine`) is fully specified.
Exactly one concrete implementation per interface is where real
implementation work should start (`AnthropicProvider` for semantics —
contact-sheet + structured JSON output is squarely Claude's strength, and
it keeps the eval loop single-vendor while L2 is being built at all;
`RemotionEngine` + `FfmpegEngine` for rendering, see §4 above and
`BUILD_ORDER.md`). The other stubs (`GeminiProvider`, `LocalProvider`,
`RevideoEngine`) exist so the *shape* of a second implementation is never a
surprise, but stay `NotImplementedError` until there's a concrete reason
to fill them in (cost comparison, a local-only privacy requirement, a
license-driven renderer swap).

---

## 6. Beat-snap needs one definition, not two

The spec mentions "snap to the beat grid" in two places — §5.1
(`duration_flex.snap: "beat"`) and §6 step 4 (matcher "snap the cut to the
beat grid with the preserved `median_cut_offset_frames`") — without ever
writing down the actual snapping algorithm. Left implicit, this gets
implemented twice, slightly differently, once in `compiler/` and once in
`matcher/`, and they drift.

**Fix:** `compiler/beat_snap.py` owns the one definition
(`snap_duration_to_beat`), used by both the compiler (to derive
`duration_flex` bounds) and the matcher (to pick the actual bound asset's
in/out point). The definition: land the *out* point at
`nearest_beat_time - (median_cut_offset_frames / fps)`, clamped to
`[min_s, max_s]`; if no beat falls in the window, fall back to the
unsnapped duration and set a confidence flag rather than snapping outside
the allowed window. The signed offset (editors cut 1-3 frames *before* the
beat) must never be normalized to zero — that's a correctness bug, not a
simplification, and it's called out at the point of measurement in
`signals/audio.py` too so it can't quietly get "fixed" by someone who
doesn't know it's intentional.

---

## 7. Matcher scoring needs explicit weights

Spec §6 names the *inputs* to asset-slot scoring (CLIP similarity,
face/shot-type/motion match) and the *solver* (Hungarian algorithm) but
never defines how the inputs combine into the scalar the solver minimizes.
Left unspecified, this becomes ad hoc code inside `assign.py` that nobody
can tune or unit-test in isolation.

**Fix:** `matcher/score.py` owns `SCORE_WEIGHTS` and `score_pair()` as a
named, tunable, independently-testable function. Starting weights (0.40
CLIP similarity, 0.25 face match, 0.20 shot-type match, 0.15 motion-pref
match) are placeholders to tune against golden-set human A/B ratings in
Phase 3 — they are not considered final, but they exist as a concrete
starting point rather than "figure it out when you get there."

---

## 8. Grade/LUT: resolved now, not left as an open question

Spec §3.5 already describes computing a "3D-LUT approximation" for grade,
while §14 open question #3 recommends storing grade stats but *not*
applying them in v1 — those two sections contradict each other if read
literally. This scaffold resolves it at the schema level:
`schemas.models.Grade` has descriptive fields (`contrast`, `saturation`,
`temp`) plus `lut_available: bool = False`. `signals/effects.py:grade_stats()`
computes only the descriptive stats and must return `lut_available=False`;
LUT synthesis is not implemented until that default is deliberately
flipped, at which point it's a schema-compatible addition, not a breaking
change.

---

## 9. Cache takedown path (gap not in the original spec)

Spec §2.3/§8.5 treats hash-based caching as a pure cost win ("the single
biggest cost saver") and §8.1's legal analysis is thorough on ToS/licensing
but never closes the loop on: *what happens when a rights holder or a user
asks for their content to be removed from a cache shared across all
users?* An indefinitely-retained, cross-user cache of third-party video is
itself a liability surface the spec doesn't address.

**Fix:** `ingest/cache.py` owns `purge(content_hash, reason)` as a
first-class operation from the start, not a Phase-5 afterthought — wire it
to an operator-accessible path (admin CLI or endpoint) no later than
Phase 4/5, per `BUILD_ORDER.md`. This is cheap to build now and expensive
to retrofit onto a cache design that never considered deletion.

---

## 10. Two-tier eval: golden set + synthetic fixtures

Spec §12 correctly says "build the eval harness in Phase 1, not later" —
agreed, and this scaffold keeps that. But a 30-video hand-annotated golden
set (§12) is too slow and too expensive to be the *only* test signal
during day-to-day development of `signals/` and `compiler/` — you don't
want to run real PySceneDetect + OCR + librosa on real video just to check
that `cuts.reconcile_detectors` merges two boundary lists correctly.

**Fix:** `eval/fixtures.py` is a second, fast tier — synthetic,
hand-constructed inputs (a boundary list, a motion curve, a beat grid +
cut list) with known expected outputs, used in ordinary unit tests
(`tests/signals/`, `tests/compiler/`, `tests/matcher/`). The golden set
(`eval/golden/`, `eval/run.py`) remains the *regression gate* — the thing
that blocks a merge — but it is not the thing a developer runs on every
save.

---

## 11. Missing CLI entrypoint

Spec §11 Phase 1 is explicitly "CLI only... print an Edit Trace JSON," but
§13's repo layout has no `cli/` directory at all — Phase 1's own success
criterion has nowhere to live in the originally-specified tree.

**Fix:** added `cli/analyze.py` as the Phase 1 entry point
(`python -m cli.analyze <source> --out trace.json`). This is deliberately
the first piece of glue code that should become real (see
`BUILD_ORDER.md` Phase 1).

---

## 12. Repo layout additions vs. spec §13

| Added | Why |
|---|---|
| `common/` | Shared config/logging/types so tunables (min_scene_len, OCR fps, etc — all called out by name in the spec) live in one place instead of being hand-copied into each module. |
| `cli/` | See §11 above. |
| `tests/` (mirroring `signals/`, `compiler/`, `matcher/`) | Unit-test home for the fast eval tier (§10 above); not mentioned in spec §13 at all. |
| `render/interface.py` | The engine abstraction boundary — implied by §7.1's "build the renderer behind an interface" instruction but not represented as a file in §13's flat `revideo/ remotion/ effects_library/` listing. |
| `schemas/generate_json_schema.py` | Makes the "Pydantic is canonical" decision (§2 above) mechanical instead of a convention people forget. |
| `ingest/cache.py::purge()` | See §9 above. |
| `eval/fixtures.py` | See §10 above. |

Nothing was removed from §13's layout; `signal/` was renamed to `signals/`
(§1) and `api/config.py` was added to separate deployment config from
pipeline config (`common/config.py`).

---

## 13. Defaults pinned for the open questions in spec §14

The original spec left five questions open "to resolve before Phase 2."
A scaffold can't be built without picking *something* for each — here is
what this scaffold assumes, and where to change it if you disagree:

1. **Local-first or hosted-first?** → **Local-first.** MCP stdio transport
   is the Phase 4a deliverable; hosted HTTP+OAuth is Phase 4b. Local-first
   sidesteps most of §8.1 (rights) and §8.2 (ingest fragility) exposure
   during early development, matching the spec's own reasoning. Change:
   `mcp/server.py` — build `run_http_server` out and flip the default
   deployment mode.
2. **Renderer license** → **Remotion primary.** See §4 above.
3. **Grade/LUT recovery** → **Stats only, no LUT synthesis in v1.** See §8
   above.
4. **Template library sourcing** → **User-analyzed only in v1.** No
   pre-seeded third-party templates ship until there's an explicit legal
   sign-off; `mcp.tools.search_library` and the Phase 5 library work
   should be built against user-generated templates first. Change this in
   `BUILD_ORDER.md` Phase 5 once legal review actually happens.
5. **Low-confidence fallback UX** → **Partial template + flags**, per the
   spec's own recommendation (agreed as-is). Enforced structurally by
   `Template.confidence_flags` and `RenderReport.approximations` existing
   as non-optional fields on the core contracts, not bolt-on nice-to-haves.

---

## 14. What this scaffold does NOT change from the original spec

Called out explicitly so it's clear these were considered and kept, not
overlooked:

- The core rule ("the LLM never measures," evidence gating) — kept
  exactly, and pushed one level deeper into the type system (see §2).
- The audio-as-reference-never-embedded rights posture (§5.2/§8.1) — kept,
  and type-enforced (`AudioRef.embed_permitted: Literal[False]`, not just
  a runtime check).
- The five signal-extraction sub-concerns (cuts, motion, text, audio,
  effects) and their internal algorithms — kept as specified; this
  scaffold only adds the missing fallback-threshold and ordering details
  (see `signals/motion.py`, `signals/trace_builder.py` docstrings).
- The MCP tool surface (§9.3) and its design rules (§9.4) — kept
  essentially verbatim in `mcp/tools.py`, plus one concrete addition:
  `wrap_untrusted_text()` as the literal implementation of the
  prompt-injection warning the spec mentions but doesn't operationalize.
- The evaluation metric set and Phase 1 gates (§12) — kept, see §10 above
  for the one addition (fast unit-test tier alongside it).

---

## 15. L7 — Conversational interface: where it sits, and the provider abstraction

New requirement, not in the original spec: a first-class, built-in chat UI
— talk to RECUT in natural language ("make this punchier," "swap the clip
in slot 3," "recreate this edit style but slower") — backed by an LLM the
user configures directly, in addition to (not instead of) §9's MCP server.
`RECUT_SPEC.md` §9A now specifies the product surface; this section
records the two judgment calls behind it and why the more "obviously
elegant" alternative for each was rejected.

### 15.1 Decision: L7 is a sibling of L6, not built on top of it

The tempting design is: "the chatbot needs to call list_slots/match_assets/
bind/render/describe_template — L6 already exposes exactly those as MCP
tools — so make the chatbot an MCP client of your own L6 server." This
looks like reuse but is actually reuse of the wrong layer. MCP's transport
(stdio subprocess, or Streamable HTTP) exists to let a process that doesn't
already trust yours — an external agent, a hosted subscription client —
call your tools over a stable wire protocol with its own auth/session
boundary. L7's chat backend and L6's tool implementations run in the same
deployment, the same trust boundary, often the same process. Routing
through MCP's protocol to reach your own in-process functions buys zero
additional isolation and costs real things: subprocess lifecycle
management (or a loopback HTTP hop) per chat session, a second
serialization boundary where tool-call semantics can silently drift from
what `mcp/tools.py` actually does, and duplicated error-handling paths.

**What's actually worth reusing is the *operations* and their
*descriptions*, not the wire protocol.** `mcp/tools.py`'s functions are
already thin, transport-agnostic Python callables (its own docstring says
so: "MCP tools must not contain business logic, only request/response
shaping"). L7 imports them directly (`from mcp.tools import list_slots,
bind, render, ...`) and builds its tool-calling-model-facing tool specs by
wrapping each function with a JSON Schema for its parameters and reusing
its docstring, verbatim, as the tool description (`chat/tool_registry.py`,
`INSTRUCTIONS.md` Unit 4.5.1). This means a tool description written once
for the MCP surface (already held to "tool descriptions are prompt
engineering" per spec §9.4) automatically also documents the tool for
whichever chat LLM the user has configured — no parallel prompt-engineering
effort, no drift between what an external Cursor/Claude agent sees and
what the built-in chat sees.

Net effect on `RECUT_SPEC.md` §1's diagram: L7 is drawn beside L6, both
sitting on L0-L5's operations layer, not stacked on top of L6.

**The reuse is one-directional and stops at the tool surface — it does not
mean L7 gets exposed back through MCP.** Confirmed explicitly per user
clarification: the conversational interface itself (talking to RECUT in
natural language) is reachable **only** through L7's own dedicated API
(`INSTRUCTIONS.md` Unit 4.5.8's `POST /chat/{session_id}/message`). There
is no MCP tool or resource that wraps the chat loop — no
`recut.chat(...)`, no way for an external MCP client to drive a
conversation through RECUT's own L7. Any external agent that wants a
conversational front end supplies its own LLM and talks through §9's
existing MCP tool surface, exactly as before this feature existed. And the
inverse holds too: nothing else in RECUT's tool surface —
`analyze_video`, `get_template`, `match_assets`, `bind`, `render`,
`adjust_template` — grows a second, non-MCP API surface just because L7
needed one for itself. The chat endpoint is additive and scoped to L7
only; it is not a precedent for an "API-and-MCP-both" pattern anywhere
else in the system.

### 15.2 Decision: a new `chat/providers/` interface, not an extension of `semantics/providers/`

The obvious question, since `semantics/providers/` already solved "abstract
over multiple LLM vendors": should L7 reuse `SemanticProvider`? No — and
the reason isn't "not invented here," it's that the two provider sets sit
on genuinely different axes:

- **What varies.** `SemanticProvider`'s volatility is "which vision model
  is best/cheapest at evidence-gated shot labeling" — a decision RECUT
  makes internally and can revisit centrally. `ChatProvider`'s volatility
  is "which LLM subscription or self-hosted endpoint a given *user*
  already has" — a decision made per-deployment, by the user, and RECUT
  has no say in it. These are not the same knob and there's no reason to
  expect they'd ever be swapped in unison.
- **Call shape.** `SemanticProvider` is single-shot: one evidence pack in,
  one schema-validated Pydantic object out (`triage()` →`StyleSummary`,
  `deep_pass()` → `SemanticShotAnnotation`), no conversation state, no
  tool-calling loop. A chat provider's natural call is a message-history-in,
  tool-call-or-text-out loop, repeated until the model is done, with
  optional streaming for UI responsiveness. Bolting a `chat(messages,
  tools)` method onto `SemanticProvider` alongside `triage`/`deep_pass`
  would produce an interface where two of the three methods share nothing
  in shape with the third — the opposite of what an interface is for.
- **Native SDK shape.** L2's providers (Claude/Gemini today) are asked for
  one structured object matching a fixed schema. Chat providers are asked
  to run a tool-calling turn against an evolving, dozen-plus-tool surface
  that isn't fixed at build time the way `TriagePromptInputs`/
  `DeepPassPromptInputs` are. Forcing both through one interface would
  distort whichever one didn't get to keep its natural shape.

**What genuinely IS shared, and reused on purpose:** the *build discipline*,
not the code. `chat/providers/base.py` is a fully-specified ABC up front,
same as `semantics/providers/base.py` — but unlike L2 (where the spec's
"3 providers as interfaces, 1 implemented" scoping was right because only
one model actually needed to work for the eval loop to proceed), the user
explicitly wants "effectively all of them" working for chat, so the
interface-now-implement-later discipline here applies at the *method*
level (streaming is deferred, `stream()` raises `NotImplementedError` by
default) rather than at the *provider* level (all 5 requested providers get
built, see `BUILD_ORDER.md` Phase 4.5) — see `INSTRUCTIONS.md` for the
exact split.

### 15.3 Provider abstraction: shim vs. real adapter

OpenAI, NVIDIA NIM, OpenRouter, and self-hosted vLLM all speak (or can be
made to speak) the same OpenAI-compatible `chat.completions.create(...,
tools=[...])` shape — one `OpenAICompatibleProvider` base class
parameterized by `base_url`/`api_key`/`model_id`/extra-headers covers all
four; the concrete classes differ only in config (`RECUT_SPEC.md` §9A.4
has the exact deltas). This is a genuine one-shim-covers-many case for
NIM/OpenRouter in particular, since both are *designed* to be OpenAI-SDK
drop-ins. vLLM shares the wire shape but not the operational guarantee —
whether tool-calling actually works depends on the served model's chat
template and vLLM being launched with a matching `--tool-call-parser`; the
code path is shared, the reliability is not, and `INSTRUCTIONS.md` Unit
4.5.4 calls this out as a real per-deployment verification step, not a
formality.

Gemini gets a real, hand-written adapter, not a config variant of the same
base class, because its function-calling shape differs structurally, not
just cosmetically: `system_instruction` is a separate config field (not a
"system" role message), roles are `user`/`model` (not `user`/`assistant`),
a tool result goes back as a `function_response` part inside a `user`-role
`Content` (not a `tool`-role message the way OpenAI wants it), function-call
arguments arrive as an already-parsed dict rather than a JSON string
needing `json.loads`, and a single turn can carry multiple `function_call`
parts with no provider-issued call id (the adapter has to synthesize one).
Trying to route Gemini through the OpenAI-compatible base class would mean
either lying to it about message roles or silently dropping the
multi-call-per-turn case — a real adapter is the only honest option.

### 15.4 The evidence-gating principle generalizes to L7

Spec's central rule — "the LLM never measures, it only labels/explains what
deterministic tools found" — has an L7 analogue, made explicit by the
`adjust_template` tool added in `RECUT_SPEC.md` §9.3/§9A.3 (added while
designing this feature: without a template-mutation tool, "make this
punchier" and "recreate this edit style but slower" have no lever to pull
at all — every other example request in the ask maps onto an existing tool,
this one didn't). `adjust_template`'s `changes` argument is a small, fixed,
schema-validated vocabulary (`global_duration_scale: float`,
`energy_bias: "punchier"|"calmer"`, bounded `slot_overrides`) — the chat
model picks a knob position from that constrained schema; it never emits a
raw `duration_s` or effect parameter for an individual shot "from vibes."
RECUT's own deterministic code (reusing `compiler/beat_snap.py`, unchanged)
computes the actual new numbers from the chosen knob. This keeps L7 inside
the same trust boundary the rest of the system already enforces: the model
chooses intent, deterministic code computes the edit.

### 15.5 Session storage and untrusted text

Chat sessions are persisted in Redis, reusing the job-store infrastructure
already built for §9.4's async job pattern (`api/workers.py`), keyed by
`session_id`, TTL'd — not a new storage dependency. Revisit Postgres-backed
persistence only if cross-device session continuity becomes a real
requirement (same "resolve now with a pinned default, revisit if a concrete
need shows up" posture as §13's open questions above).

The one risk this section calls out explicitly: any OCR/transcript/caption
string a tool result surfaces into the conversation (e.g. `describe_
template`'s output, or a `get_trace` call the chat model makes on its own
initiative) **must** be passed through the existing `mcp.tools.
wrap_untrusted_text()` — reused, not reimplemented — before it re-enters
the model's context. This is arguably a bigger deal here than in the
external-agent MCP case: an MCP client like Cursor is a tool a developer is
already treating skeptically; L7's chat model is a first-party surface an
end user is casually chatting with in real time, exactly the context where
a prompt-injection payload embedded in a scraped video's on-screen text is
most likely to be trusted at face value.
