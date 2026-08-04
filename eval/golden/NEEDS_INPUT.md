# Blocked on real video input

Unit 0.3 / Unit 1.19 require 3 (then 20+) hand-annotated real short-form
videos per `INSTRUCTIONS.md`. This cannot be fabricated by an agent:

- Ground truth must come from a human scrubbing a real video frame-by-frame
  ("there is no shortcut here" - INSTRUCTIONS.md Unit 0.3).
- Bulk/automated scraping of IG/TikTok is explicitly out of scope
  (RECUT_SPEC.md sec 8.1, DESIGN_NOTES.md "Legal posture") - only
  user-uploaded files or user-authorized single-URL pulls are supported.

**What's needed from you to unblock Unit 0.3 / the Phase 1 gate (Unit 1.19)
- two acceptable paths, use whichever is easier per video:**

**Path A - raw video + hand annotation (original ask):**
1. 3 short-form videos (any genre, ideally spanning talking-head/product/
   dance/text-tutorial/b-roll) you have the rights to use - either local
   files or URLs you're authorized to pull - dropped somewhere I can read
   them (e.g. a local folder path), plus
2. Hand-verified ground truth for each: cut timestamps + type, text layer
   strings/timing, approximate tempo - or your go-ahead for me to
   hand-label them myself by scrubbing frame-by-frame once files exist.

**Path B - raw video + editor project file (new, much faster when
available):** if you (or a creator you're asking on LinkedIn) still has
the **project file** the video was edited in - `.fcpxml` (Final Cut Pro
X), a Premiere Pro project exported as "Final Cut Pro XML" (File > Export
> Final Cut Pro XML - a normal one-menu export, not a special ask), or a
native `.otio` - send that alongside the video. `eval/golden/
import_project_file.py` (Unit 0.4, see `INSTRUCTIONS.md`/`DESIGN_NOTES.md`
sec 16) parses exact cut timestamps and transition boundaries out of it
directly via OpenTimelineIO - minutes of parsing instead of hours of
frame-scrubbing. I still do a quick human pass against the video before it
counts (same done-criterion as Path A), but that pass is much faster when
starting from a machine-parsed draft than from zero.

**Important limits on Path B, so nobody wastes effort:**
- It only reliably gives cut-boundary and transition-type ground truth.
  Text-layer (on-screen caption/graphic) timing is best-effort at most -
  it only works if the project has a dedicated title/graphics track with
  literally-named clips, and even then box/font/style are never
  recoverable this way. Most of the 20-video text-layer-IoU gate still
  needs real hand-verified `text_layers` data, from Path A or a manual
  pass on top of a Path B draft.
- **CapCut and After Effects project files are explicitly out of scope
  for Path B.** CapCut's format is proprietary/undocumented with no OTIO
  adapter; After Effects text layers are frequently expression-driven
  rather than keyframed, so exact timing often isn't recoverable even
  from a successful parse. If that's what you (or a donor) has, go
  through Path A instead - don't spend time trying to export/convert a
  CapCut or AE project for this.
- A project file alone, with no matching video, isn't useful - the video
  is still what gets evaluated against; the project file only removes the
  scrubbing labor, not the footage requirement.
- Don't send the raw project file to live in git long-term either (same
  reasoning as the video) - it often embeds your local file paths and OS
  username. A reference/copy is fine to hand over for processing; only
  the derived `annotations.json` gets committed.

**What's NOT blocked:** every Phase 1 unit's own unit tests use synthetic,
license-free fixtures (see `tests/fixtures/make_synthetic_clip.py` and
per-unit synthetic test cases in `tests/signals/`) and do not require real
video. Implementation proceeds without waiting on this - only the final
Unit 1.19 gate numbers (cut-boundary F1 >= 90%, text IoU >= 85% over a real
20-video set) are blocked until real footage is supplied.

## Public datasets checked, not used - so nobody re-investigates these

Before posting the LinkedIn ask, checked whether any existing public
dataset could shortcut the golden set. Findings, so this isn't repeated:

- **AutoTransition (`yaojie-shen/AutoTransition` on Hugging Face)** -
  annotations are **CC-BY-4.0** and genuinely well-labeled (transition
  name/start/end per cut), but every entry's `url` field points at
  `api.huoshan.com/.../_playback/?...&intranet=1` - a ByteDance-internal
  playback endpoint. Verified directly: `curl` against one of these URLs
  returns `502`, confirming it's unreachable from the public internet, not
  just slow. The only way to get actual video bytes is the dataset's
  bundled archive - a **53GB file split across 13 parts** - which isn't
  worth downloading to pull a handful of golden-set clips. License is
  fine; logistics aren't. Not used.
- **VEU-Bench** - repackages AVE (real movie scenes - almost certainly
  rights-restricted regardless of the wrapper's own Apache-2.0 tag, since
  a license on an aggregator's annotations doesn't launder the rights of
  bundled third-party movie footage) plus the same AutoTransition data
  above. Not used, for both reasons.
- **AutoShot** - code is MIT, but the actual video files are NOT included
  in the release at all (external Baidu Pan / Google Drive links) and no
  license is stated for the video data itself, separate from the code.
  Unclear rights on the underlying footage. Not used.
- **BS-BGM500** - could not locate an actual public dataset repo/release
  at all despite it being referenced in search results tied to a
  background-music-generation paper. Not used (unreachable).

Net effect: no shortcut found. The LinkedIn ask (Path A/B above) remains
the real way to grow this set.

## Phase 3 Unit 3.3 gate - blocked the same way, different resource

`AnthropicProvider.triage()` is implemented and unit-tested (fake-client
request/response shape, `tests/semantics/test_anthropic_provider.py`), but
its own done criterion - "running triage() against 3-5 real videos produces
a StyleSummary that reads as a plausible description when you compare it to
the actual video" - needs two things neither present in this environment:

- a real `ANTHROPIC_API_KEY` (none set - real calls cost real money, not
  something to fabricate a "pass" for), and
- real short-form video content (same blocker as Unit 0.3/1.19 above - only
  synthetic fixtures exist).

Same posture as the Phase 1/2 gates: implementation proceeds, only the
human/resource-gated numeric verification waits. Unblock by supplying an
API key (env var `ANTHROPIC_API_KEY`) plus 3-5 real videos, or explicit
go-ahead to run this against whatever real footage eventually arrives via
the Path A/B ask above.

## Phase 3 Unit 3.6 gate - partially covered, full variety still blocked

`matcher/probe.py::extract_asset_features()` is implemented and tested
against two REAL fixtures (not fabricated): `tests/fixtures/
synthetic_face_clip.mp4` (a real public-domain NASA photo,
`skimage.data.astronaut()`, muxed with the project's existing real
Windows-SAPI TTS speech fixture - see `tests/fixtures/make_face_clip.py`
for why a drawn "face" wouldn't exercise the real Haar-cascade path at
all) and the existing `synthetic_clip.mp4` (no face, no real speech). This
covers the has_face / has_speech axes with one real positive and one real
negative example each.

What's still blocked: the unit's own done criterion asks for "5-10 varied
local test clips (different orientations, with/without faces, with/without
speech)" - that breadth (multiple real people, real orientations, real
b-roll vs talking-head vs product-shot variety) needs real donated footage,
same blocker as everything else in this file. Not urgent to unblock
specifically for this unit - the 2 real fixtures already exercise every
code path; more variety would sharpen confidence in the coarse shot-type/
motion-score heuristics, not change the implementation.

## Units 2.9 and 3.9 - blind-viewer eval gates, both blocked (chained)

Neither has anything left to build - both are pure human-evaluation
protocols, not code:

- **Unit 2.9** (Phase 2): 10 templates rendered with HAND-assigned real
  footage, shown to 5 blind human viewers, Likert-scored against the
  original edit. Needs real short-form source videos (same blocker as
  Unit 0.3/1.19) AND 5 actual human raters - neither exists in this
  environment.
- **Unit 3.9** (Phase 3): repeats Unit 2.9's exact protocol but with
  Unit 3.8's matcher auto-assigning footage from a REAL candidate-clip pool
  per template (varied enough that the matcher has genuine choices to
  make) instead of hand-assigned clips, then compares the resulting score
  against Unit 2.9's number using a margin chosen *before* looking at the
  result. Explicitly depends on Unit 2.9's baseline (BUILD_ORDER.md/
  INSTRUCTIONS.md's own stated dependency) - blocked transitively even if
  a real clip pool existed, since there is no Unit 2.9 number to compare
  against yet.

Not something to fabricate a number for either way. Unblock by supplying
real footage (Path A/B above) and, when the time comes, help lining up 5
people willing to give Likert ratings on 10 short renders.
