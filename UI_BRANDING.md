---
doc: RECUT UI Branding & Design System
version: 0.1.0
status: source-of-truth for the Phase 5 web UI and any local-app surface
audience: Sonnet (or any engineer/agent) implementing RECUT's product surface
companion-files:
  - RECUT_SPEC.md            # product spec, §9.3 tool surface, §11 build order (Phase 5)
  - DESIGN_NOTES.md           # scaffold deviations; §7 (Grade/LUT), §9 (cache purge) inform report/UI copy
token-source-of-truth: web/styles/recut-tokens.css   # authoring target; this file's frontmatter mirrors it
---

# RECUT — UI Branding & Design System

This is the design system for RECUT's product surface: the Phase 5 web UI
(`RECUT_SPEC.md` §11) and any local-app window wrapping the same API. It
exists so an engineer or agent can build the UI without inventing taste,
without a design review round-trip, and without producing the generic
AI-tool look this document explicitly rules out in §8.

**How to use this file.** Section order matches the shape of the request
that produced it. Every non-obvious decision names the rule that drove it,
in the form `[source: file → rule name]`. If you disagree with a decision,
change the decision **and this document**, the same discipline
`skills/impeccable/AGENTS.md` enforces for its own DESIGN.md ("if you
disagree... change this document too so the next person doesn't have to
reverse-engineer which version is current" — the identical instruction
appears in `DESIGN_NOTES.md`'s own preamble, so this project already
holds itself to it twice over).

---

## 0. Methodology: how this document was built, and from what

Two reference systems shaped the *process*, not just the content, of this
document. Neither is RECUT's brand — RECUT is not Impeccable and is not
the shoplifting-detection project living in the template's `claude.md`.
What transfers is structure and rule-application discipline.

### 0.1 What transferred from `skills/impeccable`

Impeccable is a design-taste system for AI coding agents, shipped as a
skill (`skill/SKILL.src.md` + `reference/*.md`) plus a live DESIGN.md
format. Four things transferred directly:

1. **The DESIGN.md shape itself.** Impeccable's own `DESIGN.md` is a YAML
   frontmatter block of raw token values (`colors`, `typography`,
   `rounded`, `spacing`, `components`) followed by numbered prose sections
   ending in a **Do / Do Not** list, with an explicit note that the
   frontmatter "mirrors" a real CSS file and must be updated together.
   `§0-§10` of this document reproduce that shape for RECUT: a token
   frontmatter block above (mirroring `web/styles/recut-tokens.css`,
   which does not exist yet — building it is the first implementation
   task this document implies), numbered sections below, a Do/Do Not
   list in §8.

2. **PRODUCT.md's register.** Impeccable's `PRODUCT.md` states Users,
   Product Purpose, Brand Personality (a three-word compression),
   Anti-references, Design Principles, and Accessibility commitments, in
   that order, before any visual system is discussed. §1 of this document
   follows that exact order for RECUT.

3. **The Modes axis (`CLAUDE.md`, "Modes" section).** Impeccable v4
   classifies every surface as Persuade / Operate / Read / Experience —
   *per surface*, not per project, because "a tool's landing page is
   Persuade even though the product is Operate." This is the single most
   load-bearing transfer in this document: **RECUT's web UI is classified
   Operate throughout**, with the `describe_template` breakdown carrying
   a secondary Read quality (§1.4). Every subsequent color, type, spacing,
   and motion decision cites the Operate-mode guidance in the matching
   `reference/*.md` file rather than the Persuade-mode guidance, because
   RECUT's UI is a tool an editor completes tasks in, not a landing page
   that has to sell on sight.

4. **Command-file rule structure**, applied section-by-section below:
   - `reference/colorize.md` → color roles, OKLCH-authoring rule, contrast
     table, "derive secondary text from surface hue, not washed-out gray."
   - `reference/typeset.md` → the 16px body floor, 45–75ch measure,
     tabular-numeral rule, "role names describe purpose, not values."
   - `reference/layout.md` → the 4-unit spacing-scale rule, the squint
     test, "variation is not a goal by itself."
   - `reference/animate.md` → the duration table, the ban on bounce/elastic
     easing, the "one focal moment" allowance, `prefers-reduced-motion`
     handling.
   - `reference/audit.md` → the P0–P3 severity taxonomy and five-dimension
     score, adapted in §9 into RECUT's own UI quality gate.
   - `PRODUCT.md`'s **Anti-references** and **Design Principles** →
     directly quoted and applied to RECUT-specific failure modes in §8.
   - `README.md`'s named anti-patterns (`overused-font`, `icon-tile-stack`,
     nested cards, gray-on-color, bounce easing) → cited by name in §8
     because they are the *actual detector rule IDs* Impeccable ships,
     not paraphrases.

   What did **not** transfer: Impeccable's own palette (kinpaku gold /
   verdigris patina / lacquer black), its Alumni Sans display face, and
   its brand voice ("expert, decisive, editorial"). Those are Impeccable's
   brand commitments, not a universal taste, and reusing them on RECUT
   would violate the very rule that makes Impeccable coherent: colors and
   type must come from *this* product's meaning, never a default or a
   borrowed identity (`reference/colorize.md`, "Audit before choosing" —
   "choose hue from product meaning... never from a default category
   association").

### 0.2 What transferred from `skills/ai-agent-foundation-template`

This repo (as cloned) is mid-repurpose for an unrelated computer-vision
project — its `claude.md` describes a shoplifting-detection pipeline that
has nothing to do with RECUT. Its content is not usable; its **structure**
is, and three conventions transferred:

1. **The "Project DNA" file shape.** Its `claude.md` runs: Mission Context
   → Architecture Directives → Core Runtime Layers (a named table of
   pipeline stages) → Execution Discipline → **Decision Record** (an
   append-only, timestamped log with the explicit instruction "any
   architectural change must be appended to this file under a timestamped
   heading"). This document borrows that exact skeleton: §1 is Mission
   Context, §8 (Do/Do Not) is Architecture Directives, §5's screen table
   is a Core Runtime Layers analogue (RECUT's own layers are its five
   required screens, not camera/detect/alert), and §11 is a live Decision
   Record, seeded and ready for future timestamped entries.

2. **A single registry plus a routing table, not scattered ad hoc lists.**
   `skills.md` is one inventory of every installed skill; a separate
   `SKILL_ROUTING_TABLE.md` maps *task domain → which skill(s) apply*.
   Applied here: §10 is a single **Component Registry** (every reusable
   RECUT UI primitive, named once), and §10.2 is a **Screen → Component
   Routing Table** mapping each of the five required screens to exactly
   which primitives and tokens it consumes — so an implementer never has
   to guess which button variant belongs on which screen.

3. **A loader script that points at an external source of truth rather
   than re-declaring it.** `skills.sh` is four lines that pull named
   sources into `.agents/skills/`; it does not re-author skill content
   inline. The frontmatter block at the top of this document plays the
   same role: it names `web/styles/recut-tokens.css` as the real source
   of truth and instructs that the frontmatter must be kept in sync with
   it, rather than treating this markdown file as the only place values
   live (same discipline Impeccable's own DESIGN.md states verbatim).

What did **not** transfer: any of the specific 60+ (or, in the routing
table, 1510) bundled skills, the shoplifting/camera domain content, or
the multi-harness distribution machinery (`.claude/`, `.cursor/`, etc.) —
none of it is relevant to a one-product UI spec.

---

## 1. Brand identity

### 1.1 Register (mirrors `PRODUCT.md`'s Users / Purpose / Personality shape)

**Users.** Creators and small edit shops who see a short-form video that
performs, and want to run their own footage through its exact structure —
cut timing, motion, text choreography, beat-lock — without reverse
engineering it by hand in CapCut. They are editors first, "AI tool"
customers second. They already know what a beat grid and a cut point are;
do not explain those terms to them.

**Product purpose.** RECUT turns a video into three things a human and a
machine can both act on: a measured **Edit Trace**, a re-shootable
**Template** with the footage removed, and a **render** with the user's
own clips in place. Success looks like: an editor opens the app, drops in
footage, and gets back a cut that a blind viewer rates "same edit" —
not a cut that merely *resembles* one (spec §11, Phase 2 success
criterion: "5 blind viewers rate the re-creation ≥4/5 for 'same edit'").

**One-sentence positioning** (tied directly to the decompose → template →
re-render value chain in spec §0.1):

> **RECUT measures how a video was cut, writes that measurement down as
> instructions a human can follow, and rebuilds the same edit with
> different footage.**

Do not shorten this to "AI video remixer" or "recreate viral edits with
AI" in any UI copy, marketing surface, or empty-state string. Both phrases
hide the thing that makes RECUT trustworthy — that a deterministic
pipeline measures the cut and an LLM only labels what was measured (spec
§1, "Core design rule") — behind a generic AI-tool promise. Every user of
the product already knows AI-generated video is unreliable; the product's
entire pitch is that this specific pipeline is not guessing (`PRODUCT.md`
Anti-references, applied: "this product is for people who already know
they have a problem; we solve it, we don't teach it" — RECUT's problem is
distrust of black-box AI editing, and the copy has to sell the
measurement, not the AI).

**Three-word personality: measured, direct, unglamorous.**

- *Measured* — every claim in the UI traces to a number (a confidence
  score, a frame offset, a beat-lock ratio). No claim is asserted without
  its evidence being one click away (§4.5, §5's Evidence disclosure
  pattern).
- *Direct* — instructions read like a shot list a working editor would
  actually write: "Drop a close-up of your face reacting. Must have
  visible motion. ~1.2s." (spec §5.1's own example — this is not a
  hypothetical tone sample, it is the literal `human_instruction` string
  the compiler is specified to produce, and the UI's voice has to match
  it exactly or the instruction will read like two different products).
- *Unglamorous* — no hero shots of the product doing something impressive,
  no "your video, reimagined" copy, no confetti on render-complete beyond
  the one authorized focal moment in §7. The product's credibility is the
  render report telling you exactly what it approximated (spec §7.3,
  §8.4). A tool that admits its approximations reads as more trustworthy
  than one that hides them, which is the entire competitive position spec
  §8.4 stakes out ("Ship the render report so the user knows exactly what
  was approximated").

**Anti-references** (`PRODUCT.md`'s Anti-references section, applied to
RECUT specifically, not copied from Impeccable's list):

- Generic "AI video tool" marketing: purple-to-blue gradients, glowing
  particles, a hero video that autoplays a flashy remix. RECUT's actual
  hero moment, if it ever needs one, is a side-by-side of a real Edit
  Trace timeline next to the source video — the product demonstrating
  measurement, not vibes.
- "Reimagine your content" / "unlock virality" copy register. RECUT is a
  precision instrument, not a growth-hacking tool. Voice is closer to a
  color-grading suite's release notes than a creator-economy landing page.
- Hedging language anywhere a measured value exists. "This might be a
  face shot" is wrong; "Confidence: 61%" is right. Hedging is for the
  cases spec §14 Q5 actually calls for — low-confidence partial output —
  and there it is expressed as a **number and a flag**, never as vague
  prose (§4.4).
- A gamified aggregate score anywhere in the product (see §8, item 9).

### 1.2 Name treatment

**RECUT** — always set in full capitals, no lowercase wordmark variant,
no tagline stacked underneath in normal use.

- **Wordmark face:** IBM Plex Mono, weight 500 (Medium), letter-spacing
  `+0.08em`. This is a deliberate deviation from the usual practice of
  setting a wordmark in the display/UI sans (Impeccable, for comparison,
  holds its wordmark in Alumni Sans specifically because the display
  cut reads too thin at lockup size — see `DESIGN.md` §4). RECUT's
  reason is different and specific to this product: the brand's whole
  claim is measurement — timecodes, frame offsets, confidence
  percentages — and every one of those is set in Plex Mono elsewhere in
  the UI (§3). Setting the wordmark in the same face as a timecode
  readout is the visual argument for the brand in four letters; setting
  it in the body sans would make it a generic startup logotype.
- **Mark:** two vertical hairlines (1.5px, full lockup height) with a
  single diagonal stroke crossing between them at 20° — literally a cut
  mark on a strip of film/tape. Rendered in Amber (`--rc-amber-500`) on
  dark canvas, in `--rc-ink` (near-black) on light canvas. No rounded
  square container. No abstract "play button" or "waveform" cliché mark;
  those are the two most overused glyphs in video-tool logos and neither
  depicts what RECUT actually does (measuring *cuts*, not playing or
  hearing).
- **Lockup:** mark, 12px gap, wordmark. Minimum clear space equal to the
  mark's width on all sides. Never place the lockup on a busy thumbnail
  or timeline background without a solid-fill chip behind it.

### 1.3 Tone of voice

Second person, present tense, active voice, no hedging modal verbs
("might," "could," "try") anywhere a measured value or a direct action is
available — `PRODUCT.md`'s Anti-references list bans hedging outright and
`docs/STYLE.md` (referenced from `AGENTS.md`) enforces it at the prose
level for Impeccable's own copy; RECUT adopts the same discipline for its
own UI strings, human_instruction text, and render-report language.
Concretely:

| Situation | Write this | Not this |
|---|---|---|
| Empty slot | "Drop a close-up of your face reacting. Must have visible motion. ~1.2s." | "You could try adding a face shot here if you have one." |
| Low-confidence binding | "62% match. Verify before rendering." | "This might not be quite right." |
| Approximated effect | "Speed ramp approximated as 3 linear segments." | "We tried our best to recreate the speed effect." |
| Render done | "Rendered. 2 approximations — see report." | "Your amazing video is ready! 🎉" |
| Ingest failure | "Couldn't download from that URL. Upload the file instead." | "Oops! Something went wrong." |

### 1.4 Mode classification per screen

Per `CLAUDE.md`'s Modes axis, classified per surface, not per project:

| Screen | Mode | What that means here |
|---|---|---|
| Edit Trace viewer | **Operate** | Stability and scanability first; this is a working timeline, not a showcase. |
| Template slot-grid | **Operate** | Predictable card geometry; density matches editing-tool norms, not marketing-grid norms. |
| Asset matcher | **Operate** | Every override must be reachable in one action (`reference/operate.md`'s general Operate guidance: task completion is the success metric). |
| Render report | **Operate** + light **Read** | It's a task surface (approve/re-render) but the individual entries are read as a document — full sentences, not just icons. |
| `describe_template` breakdown | **Read** primary, **Operate** secondary | This view exists to be *read* — by a human or pasted to an agent — before any action is taken on it. Typography and measure rules for long-form reading (§3) apply here more than anywhere else in the product. |

---

## 2. Color system

### 2.1 Rule basis

Per `reference/colorize.md`: "prefer OKLCH because lightness and chroma
can be adjusted predictably," "choose hue from product meaning... never
from a default category association," and "on colored surfaces, derive
secondary text from the foreground or surface hue rather than washed-out
generic gray." All hex values below are the canonical spec (exact,
copy-pasteable); author them as `oklch()` custom properties in
`web/styles/recut-tokens.css` per that rule, and **re-verify every
foreground/background pair with an actual contrast checker after
conversion** — per the same file's instruction, "do not rely on eyesight
alone," which applies equally to a value handed to you in a spec document.
The table in §2.5 states the required ratios; it does not certify that
the hex values below already clear them to three decimal places, because
no tool that could verify that was run against these exact sRGB values.
State that plainly if you find a pair that fails on recheck, and shift
lightness (not hue) to fix it, per colorize.md's ramp guidance.

### 2.2 Why this palette, not a generic dark-mode-plus-accent palette

Two deliberate hue choices anchor the system, each tied to something
RECUT's spec actually measures, not to a category default:

- **Keycode Amber** (primary/brand) — named for the amber ink used to
  print edge/key-code numbers on film stock and the amber LED timecode
  readouts on tape decks. RECUT's whole product is built on frame-accurate
  timecode (spec §3.6's `t_in`/`t_out`, §3.4's beat grid, §7.3's frame
  counts). An amber "measurement" accent is meaningful here in a way a
  default blue or purple is not.
- **Trace Green** (validated/success) — the "locked in, confirmed"
  color, used only for states that a deterministic check has actually
  passed (slot filled, template compiled, render complete). Never
  decorative.

This explicitly avoids the two hues `PRODUCT.md`'s Anti-references and
`reference/colorize.md`'s own contrast guidance both warn against for
generic reasons and that most AI-coding-tool dark UIs reach for by
reflex: **purple** (no semantic tie to anything RECUT does) and **cyan
as a static brand color** (the generic-AI-tool "cyan-on-black" tell named
explicitly in `PRODUCT.md`). Blue survives in this system only as a
transient, functional "processing" signal (§2.4), never as a resting UI
color — which is exactly the distinction that keeps it from reading as
the cliché.

### 2.3 Dark theme (default)

RECUT defaults to dark. Every professional NLE it's positioned adjacent
to (Resolve, Premiere, Avid) defaults dark for the same reason: editors
grade and cut in low-light rooms, and a bright chrome around the actual
footage biases color judgment. Values are tinted, never pure black, per
the general "do not use pure black or pure white" rule Impeccable states
as a flat Do-Not and this document adopts as a universal one, not an
Impeccable-specific one — pure black crushes shadow detail in adjacent
video thumbnails and reads as an uncalibrated monitor.

**Surfaces**

| Token | Hex | Use |
|---|---|---|
| `--rc-canvas` | `#0E1012` | App background |
| `--rc-surface-1` | `#16191C` | Panels, sidebar, timeline track lanes |
| `--rc-surface-2` | `#1D2124` | Raised cards (slot cards, list rows) |
| `--rc-surface-3` | `#23282B` | Popovers, tooltips, dropdown menus, modals |
| `--rc-border` | `#2C3236` | Default hairline / divider |
| `--rc-border-strong` | `#3A4046` | Active/focused container border |

**Text**

| Token | Hex | Use |
|---|---|---|
| `--rc-text-primary` | `#EDEEF0` | Headings, primary labels, body copy |
| `--rc-text-secondary` | `#AEB4B9` | Secondary copy, inactive labels |
| `--rc-text-tertiary` | `#7B8288` | Meta, timestamps, table chrome |
| `--rc-text-disabled` | `#4B5156` | Disabled control labels |

**Keycode Amber** (brand / primary action / low-confidence flag —
disambiguated by shape and icon, not a second hue; see §2.6)

| Token | Hex | Use |
|---|---|---|
| `--rc-amber-50` | `#2A1F0E` | Tinted background fill (badges, banners) |
| `--rc-amber-300` | `#FFC876` | Hover/lift state |
| `--rc-amber-500` | `#F5A623` | Base — primary button fill, brand mark |
| `--rc-amber-600` | `#D88E12` | Active/pressed |
| `--rc-amber-text` | `#FFD79A` | Small amber text/links on dark surfaces |

**Trace Green** (validated / success / filled / render-done)

| Token | Hex | Use |
|---|---|---|
| `--rc-green-50` | `#0E2420` | Tinted background fill |
| `--rc-green-300` | `#6FE6C4` | Hover/lift |
| `--rc-green-500` | `#2BB99C` | Base — filled-slot border, success badge |
| `--rc-green-600` | `#1E9A81` | Active/pressed |

**Flag Red** (error / destructive action only — never a soft warning)

| Token | Hex | Use |
|---|---|---|
| `--rc-red-50` | `#2B1214` | Tinted background fill |
| `--rc-red-300` | `#FF9C9C` | Hover/lift |
| `--rc-red-500` | `#E5484D` | Base — destructive button, hard failure state |
| `--rc-red-600` | `#C93A3E` | Active/pressed |

**Scan Blue** (processing/analyzing — transient/motion use only, see §2.4)

| Token | Hex | Use |
|---|---|---|
| `--rc-blue-50` | `#0F1B2B` | Tinted background fill (progress track) |
| `--rc-blue-300` | `#8FC7FF` | Sweep highlight |
| `--rc-blue-500` | `#3B82D6` | Base — progress fill, active-stage label |
| `--rc-blue-600` | `#5FA3EE` | Sweep peak (animated only) |

### 2.4 Light theme

Full parity, not a mechanical inversion (`reference/colorize.md`: "design
surface elevation and contrast explicitly; do not invert the light theme
mechanically"). Surfaces are warm-neutral paper, never pure white.

**Surfaces**

| Token | Hex | Use |
|---|---|---|
| `--rc-canvas` | `#F5F4F1` | App background |
| `--rc-surface-1` | `#FCFBF9` | Panels, sidebar |
| `--rc-surface-2` | `#FDFCFA` | Raised cards |
| `--rc-surface-3` | `#FFFFFF` | Popovers/modals (the one place pure white is acceptable: topmost, small-area, momentary surfaces, not the page ground) |
| `--rc-border` | `#DEDBD5` | Default hairline |
| `--rc-border-strong` | `#C7C2B8` | Active/focused container border |

**Text**

| Token | Hex | Use |
|---|---|---|
| `--rc-text-primary` | `#1B1C1E` | Headings, body |
| `--rc-text-secondary` | `#52565B` | Secondary copy |
| `--rc-text-tertiary` | `#7A7E82` | Meta |
| `--rc-text-disabled` | `#A8ABAE` | Disabled |

**Semantic families on light** — same hue families, re-lightened per
colorize.md's "vary lightness and reduce chroma near white" ramp
guidance, with dedicated small-text variants because the dark-mode `-500`
values do not clear 4.5:1 on a paper ground:

| Token | Hex | Use |
|---|---|---|
| `--rc-amber-fill` | `#F5A623` | Button/badge fill — pair with `--rc-ink` (`#1B1C1E`) text, not white |
| `--rc-amber-text-on-light` | `#B5730A` | Links, small amber text/icons on paper |
| `--rc-green-fill` | `#2BB99C` | Success fill — pair with `--rc-ink` text |
| `--rc-green-text-on-light` | `#128567` | Small green text on paper |
| `--rc-red-fill` | `#E5484D` | Destructive fill — pair with white text |
| `--rc-red-text-on-light` | `#B42328` | Small red text on paper |
| `--rc-blue-fill` | `#3B82D6` | Progress fill — pair with white text |
| `--rc-blue-text-on-light` | `#1D5FA0` | Small blue text/label on paper |

This split (`-fill` for large-area/control use, `-text-on-*` for small
text) is the same move `DESIGN.md` makes for its own gold-on-paper problem
(the "Gold-By-Size-On-Paper Rule": large accents keep the brand hue, small
body/label text on paper switches to a variant that actually holds
contrast). The rule transfers because it is a general truth about
mid-lightness saturated hues on bright grounds, not something specific to
kinpaku gold.

### 2.5 Semantic role → RECUT UI state map

This is the concrete mapping the brief asked for — not "primary/secondary"
but RECUT's actual states:

| UI state | Token | Where it appears |
|---|---|---|
| **Analyzing** (job running, any stage) | `--rc-blue-500` fill + `--rc-blue-600` animated sweep | Job progress bar (§5.A), stage label text |
| **Template-ready** (compile succeeded) | `--rc-green-500` badge, check icon | Template header badge, `list_slots` summary row |
| **Slot-empty** | `--rc-border` (dashed, 1.5px), no fill color at all | Unbound slot card — absence of color is the signal |
| **Slot-filled** | `--rc-green-500` solid 2px border + corner check | Bound slot card |
| **Low-confidence-flag** | `--rc-amber-500` border/badge + triangle icon + inline text | Bound-but-flagged slot, matcher banner, render report row |
| **Render-in-progress** | `--rc-blue-500` fill, staged/segmented (§7) | Render job progress |
| **Render-done** | `--rc-green-500` + one authored reveal (§7) | Render complete state |
| **Hard failure** (ingest failed, render errored) | `--rc-red-500` | Toast, inline error, destructive-confirm dialogs only |

### 2.6 Color rules (RECUT's own, in the imperative form Impeccable states its rules in)

**The Amber-Is-Attention Rule.** Amber means "a measured/derived value
that deserves your attention" whether that's a primary button (draw
attention to *act*) or a low-confidence flag (draw attention to *verify*).
The two uses never collide in practice because a button and a pill-shaped
badge-with-triangle-icon are never visually ambiguous — this is exactly
`reference/colorize.md`'s instruction that "information conveyed by color
also needs text, shape, iconography, or position," applied to justify why
one hue can carry two roles instead of inventing a fifth family.

**The Green-Means-Verified Rule.** Green never appears on anything a
deterministic check hasn't actually passed. Do not use it for "this looks
done" — only for "this slot is bound," "this template compiled," "this
render finished." A green element the user can click and get an error
behind is a broken trust contract for this specific product.

**The Blue-Is-Motion-Only Rule.** Blue never appears as a resting/static
UI color — no blue nav links, no blue static icons. It exists only while
something is actively being measured or rendered, and disappears the
moment that stage completes (converts to green or amber). This is what
keeps it from reading as the generic "AI-tool cyan" anti-pattern despite
being in the same hue family: static cyan chrome is the tell; a
transient, functional progress indicator is not.

**The Red-Is-Rare Rule.** Red is reserved for destructive actions and
actual failures. It is never used for "low confidence" (that's amber —
low confidence is an approximation to review, not an error) and never
used decoratively.

**The Evidence-Over-Decoration Rule** (derived from spec §4.3's evidence
gating, applied to color instead of model output): a color never
communicates something the underlying data doesn't support. If a slot's
binding confidence is unknown, it gets neutral chrome, not a guessed
color.

---

## 3. Typography

### 3.1 Font stack and why

| Role | Stack |
|---|---|
| UI / body | `"IBM Plex Sans", "Segoe UI", system-ui, sans-serif` |
| Data / mono | `"IBM Plex Mono", "Cascadia Code", Consolas, monospace` |

No display face. Per `reference/typeset.md`'s Operate-mode guidance:
"stability, scanability, and measure come first. A single well-tuned
family and fixed role scale are often right." RECUT's UI is Operate
throughout (§1.4); it does not need a second, heavier display face the
way a marketing surface would. Hierarchy comes from the scale, weight,
and the mono/sans split in §3.3 — not from a second family.

IBM Plex Sans is the specific choice, not a placeholder, for two reasons:
(1) it is explicitly not one of the overused defaults Impeccable's README
names outright — "Arial, Inter, system defaults" — so choosing it
directly satisfies that anti-pattern rule rather than merely avoiding
Inter by accident; (2) it ships a true monospace sibling (Plex Mono) drawn
to match x-height and stroke weight, which matters because RECUT's UI is
unusually dense with numeric data — timecodes, frame counts, confidence
percentages, beat-grid offsets — that needs a mono face to sit correctly
inline with sans body text without a visual seam.

### 3.2 Scale

16px root. Role names describe purpose, not size, per
`reference/typeset.md`: "Role names and tokens should describe purpose
rather than values."

| Role | Size | Weight | Face | Use |
|---|---|---|---|---|
| `micro` | 11px / 0.6875rem | 500, tracked +0.06em | Plex Mono | Timeline ruler ticks, frame counters |
| `caption` | 12px / 0.75rem | 400 | Plex Sans | Table cell meta, slot IDs |
| `label` | 13px / 0.8125rem | 500 | Plex Sans | Form labels, badge text, secondary buttons |
| `body-sm` | 14px / 0.875rem | 400 | Plex Sans | Default UI text — list rows, sidebar, dense controls |
| `body` | 16px / 1rem | 400 | Plex Sans | Long-form copy: render report prose, `describe_template` breakdown |
| `title-sm` | 18px / 1.125rem | 600 | Plex Sans | Slot-card title, panel header |
| `title` | 20px / 1.25rem | 600 | Plex Sans | Section header within a screen ("Text Layers", "Shots") |
| `heading` | 24px / 1.5rem | 600 | Plex Sans | Page header ("Edit Trace — reel_4821.mp4") |
| `display` | 32px / 2rem | 600 | Plex Sans | Onboarding/empty-state hero moments only |

`body-sm` (14px), not 16px, is the default control/list-row size. This is
a deliberate, cited exception to the general 16px web-body floor: per
`reference/typeset.md`, "Use 1rem / 16px as the ordinary web body floor
**unless a dense role, platform convention, or user setting justifies
otherwise**." A multi-track timeline and a slot grid are exactly that
dense role — the same one professional NLE UIs universally choose a
compact size for — so `body-sm` is used across all dense chrome, and full
`body` (16px) is reserved for the two places users actually read
sustained prose: the render report and the `describe_template` view.

### 3.3 Numeric and mono usage (a load-bearing rule for this product)

Per `reference/typeset.md`: "Use numeric, tabular, code, and label
features when their content benefits." Apply `font-variant-numeric:
tabular-nums` and the Plex Mono face to every one of the following,
without exception, because RECUT's entire credibility rests on numbers
lining up and being scannable:

- Timecodes and durations (`t_in`, `t_out`, `duration_s`)
- Frame counts and offsets (`median_cut_offset_frames`, `in_duration_f`)
- Confidence percentages and scores (`font_confidence`, matcher scores)
- Beat-grid values (`tempo_bpm`, `beat_lock_ratio`)
- `slot_id`, `job_id`, and any other identifier a user might need to
  read aloud or paste elsewhere

Never set these in Plex Sans with proportional figures. A confidence
column where "61%" and "100%" don't share a baseline width reads as
sloppy specifically because this product's pitch is precision.

### 3.4 Measure and reading rules

- Render report and `describe_template` body copy: 45–75ch measure,
  line-height 1.5 (not Impeccable's 1.8 — that value is tuned for
  Impeccable's own long-form marketing prose on a dark lacquer ground;
  RECUT's body copy is short, task-oriented paragraphs, and 1.5 keeps
  report rows scannable without excess vertical rhythm crowding out the
  data columns beside them).
- Dense list/table rows (`body-sm`): line-height 1.3.
- `describe_template` per-slot instruction text is always full sentences
  at `body` size, never truncated with an ellipsis — it is, per spec
  §5.1, "the product."

---

## 4. Spacing, layout grid, and elevation

### 4.1 Spacing scale

4-unit base, per `reference/layout.md`: "Use a documented spacing scale
rather than one-off values. A 4-unit base usually provides the useful
middle steps that an 8-only scale misses" — directly relevant here
because slot-card internal padding and timeline row heights repeatedly
need the 12px and 20px middle steps an 8-only scale skips.

| Token | Value |
|---|---|
| `--rc-space-1` | 4px |
| `--rc-space-2` | 8px |
| `--rc-space-3` | 12px |
| `--rc-space-4` | 16px |
| `--rc-space-5` | 20px |
| `--rc-space-6` | 24px |
| `--rc-space-8` | 32px |
| `--rc-space-10` | 40px |
| `--rc-space-12` | 48px |
| `--rc-space-16` | 64px |

### 4.2 Radius scale

Small radii throughout — a technical instrument, not a soft consumer app.
Pill reserved for status badges only, matching the general "no wide
rounded cards" discipline Impeccable states as a flat Do-Not.

| Token | Value | Use |
|---|---|---|
| `--rc-radius-none` | 0 | Timeline track rows, full-bleed panels |
| `--rc-radius-sm` | 3px | Buttons, inputs |
| `--rc-radius-md` | 6px | Cards (slot cards, list-row groups) |
| `--rc-radius-lg` | 8px | Modals, popovers |
| `--rc-radius-pill` | 999px | Status badges only |

### 4.3 Grid

- App shell: fixed 280px left sidebar (project/template nav) + fluid main
  column. Max content width in the main column: **1440px** — wider than a
  marketing page's typical ~1200–1320px, because this is a multi-panel
  editing tool (timeline + inspector + slot grid genuinely need the
  width; artificially narrowing it to a marketing-page measure would
  waste the exact screen real estate an editor needs).
- Slot-grid view: 12-column grid inside the main column, `--rc-space-4`
  (16px) gutters. Default slot card spans 4 of 12 (three per row on a
  1440px canvas); a "focus" view can span 6 or 12 for detail work.
- Timeline: **not** on the grid. It is a full-bleed, edge-to-edge
  horizontal region independent of the 12-column system, because a
  timeline's horizontal axis is time, not layout columns — forcing it
  into the grid would misrepresent what the axis means.

### 4.4 Elevation

Per Impeccable's general material principle (adopted here as a universal
good, not an Impeccable-specific one): hairlines before shadow, no default
card shadow, depth used only when it clarifies state.

| Token | Value | Use |
|---|---|---|
| `--rc-shadow-none` | (none) | Cards, panels — bordered by `--rc-border`, not shadowed |
| `--rc-shadow-popover` | `0 8px 24px rgb(0 0 0 / 0.35)` | Dropdowns, tooltips only |
| `--rc-shadow-modal` | `0 16px 48px rgb(0 0 0 / 0.45)` | Modal dialogs only |

Slot cards, timeline tracks, and list rows never carry a shadow. Their
state is communicated by border color and fill (§2.5), which is more
legible at a glance across a grid of 12+ cards than a subtle shadow would
be, and avoids the flat, undifferentiated "everything is a slightly
elevated card" look that shadow-by-default produces.

---

## 5. Component-level direction for RECUT's actual screens

Each screen below states: purpose, structure, and the specific states
from §2.5 it must render. Component names referenced here are defined
once in the Component Registry (§10).

### 5.A — Edit Trace viewer (shots / text-layers / audio timeline)

**Purpose.** Let a human see, and trust, exactly what L1 measured (spec
§3): every cut, every motion curve, every text layer, every beat.

**Structure.** A multi-track timeline, top to bottom:
1. **Shot track** — contiguous blocks per `shots[]`, one block per shot,
   width proportional to `t_out - t_in`.
2. **Text-layer track** — one row per concurrent text layer, chips
   positioned at `t_in`/`t_out`.
3. **Audio/beat track** — waveform (from the extracted WAV) with the
   beat grid (`beat_grid_s`) as tick marks beneath it.
4. **Playhead + frame-accurate zoom control** — the spec's own accuracy
   target is ±2 frames (§12); the UI must let a user zoom to see
   individual frames, not just seconds, or the precision the pipeline
   promises is invisible in the tool that's supposed to demonstrate it.

**Shot blocks.**
- Default: `--rc-surface-2` fill, 1px `--rc-border` separator at each cut
  boundary.
- Low detector confidence (high `residual` on the fitted motion curve, or
  low cut-type confidence): 2px `--rc-amber-500` left edge + small
  triangle badge, top-right corner. Hover reveals the evidence disclosure
  (§5.E's pattern, reused here) with the raw residual value and detector
  name (`evidence.cut_detector`, per spec §3.6).
- Transition type at each boundary is a monochrome glyph (§6), not a
  color: cut = plain hairline, dissolve = crossfade-diamond icon, whip =
  chevron-arrow, flash = starburst tick, zoom = corner-bracket. Glyphs
  turn amber only when confidence is low, same rule as blocks.
- Camera motion (`motion.primitive`, e.g. `punch_in`) is annotated as a
  small label + a mini scale/pan sparkline directly on the block, not a
  separate inspector-only view — this is the single fastes way to
  eyeball "does this shot punch in or pan" without opening a side panel.

**Beat track.**
- Beat ticks: `--rc-text-tertiary`.
- Beats the compiler actually locked cuts to: `--rc-green-500` tick +
  a small bracket connecting the tick to the shot boundary, labeled with
  the signed frame offset in `micro`/Plex Mono (e.g. `-2f`). This
  surfaces `median_cut_offset_frames` directly in the timeline — per
  `DESIGN_NOTES.md` §6, that signed offset "must never be normalized to
  zero... it's called out at the point of measurement... so it can't
  quietly get 'fixed' by someone who doesn't know it's intentional." The
  UI is exactly the second place (after the code comment) this
  intentionality needs to be visible, or a future redesign will "fix" the
  offset to zero because it looks like noise.

**Text-layer chips.**
- Neutral surface fill for all chips regardless of `role`
  (`hook_title`/`caption_burnin`/`lyric`/`label`/`cta`/`watermark`) —
  role is distinguished by a small outline icon + label text, never by a
  sixth accent hue. Per `reference/colorize.md`: "For data, use distinct
  lightness, chroma, shape, label, or pattern so color is not the only
  code" — here, shape+icon+label is the chosen code, keeping the palette
  restrained rather than adding role-specific hues nothing else in the
  system needs.
- Low `font_confidence`: same amber-edge treatment as shots.

### 5.B — Template slot-grid (empty vs. filled vs. low-confidence)

**Purpose.** Surface the `human_instruction` string as the primary
content of an unfilled slot — spec §5.1 states plainly that this field
"is the product," and the layout must treat it that way, not as a caption
under a bigger empty-frame icon.

**Slot card anatomy** (`--rc-radius-md`, `--rc-space-4` internal padding,
no shadow, bordered per state):

- **Empty** (§2.5): dashed 1.5px `--rc-border`. Content, top to bottom:
  a small empty-frame line icon (not decorative illustration — see §6),
  the `human_instruction` string at `body` size as the dominant text
  element, then a row of neutral requirement tags (`shot_type_pref`,
  `needs_face`, `motion_pref`, `role`) at `label` size below it, then the
  duration constraint as a small `caption`/Plex Mono chip: `1.2s
  (0.9–1.6s, beat-snapped)`.
- **Filled** (§2.5): solid 2px `--rc-green-500` border. Thumbnail (first
  frame or matched clip preview) fills the card as background. A scrim
  bar at the bottom of the thumbnail carries duration + match confidence
  in tabular Plex Mono. Small green corner-check, top-right.
- **Low-confidence-filled**: identical to Filled, but border is
  `--rc-amber-500` and the scrim bar carries explicit text — "62% match
  — verify" — not just a percentage number, per the Evidence-Over-
  Decoration and Amber-Is-Attention rules in §2.6.

**Grid vs. sequence.** Default view is a horizontal reorderable strip in
`order` sequence (matching how an editor actually thinks about a cut
list); a secondary grid-overview toggle exists for scanning all slots at
once. Do not default to a bento-style grid that discards sequence — order
is semantically load-bearing data here (`spec §5.1`'s `order` field), not
a display convenience.

### 5.C — Asset matcher / binding UI

**Purpose.** Score every (asset, slot) pair, propose bindings, and — per
spec §6's explicit requirement — "always let the human override. Never
silently misplace a clip."

**Structure.** Two-pane: left = asset library (thumbnail, probed
duration/orientation/motion score per spec §6.2), right = slot list
(reusing the Slot Card component from §5.B in its bound states).

**Hard requirement, stated as a layout rule, not a preference.** Every
bound slot card carries an always-visible "Change" affordance as a
persistent secondary button — never behind an overflow menu, never a
hover-only reveal. Spec §6's wording ("never silently misplace a clip")
is a correctness requirement, not a UX nicety, so hiding the override
behind an extra click or a hover state is a spec violation, not a design
taste question.

**Proactive low-confidence surfacing.** A persistent banner at the top of
the matcher, visible whenever ≥1 binding is below the confidence
threshold: "3 bindings need review" — clicking it filters to just those
slots. This exists because `DESIGN_NOTES.md` §13 item 5 makes
`Template.confidence_flags` "a non-optional field on the core contract,
not a bolt-on nice-to-have" — the UI's obligation is to surface that field
unprompted, not wait for the user to notice a subtle amber border amid a
grid of a dozen cards.

**In/out window transparency.** Each bound asset gets a small scrubber
showing the chosen sub-window against the asset's full duration, with
beat ticks overlaid — showing *why* that window was picked (motion/
quality score + beat-snap), not just presenting the result as a fait
accompli. This is the matcher's version of the Evidence disclosure
pattern (§5.E).

### 5.D — Render report (approximations made)

**Purpose.** Spec §7.3 requires "a render report listing every
approximation made." §8.4 requires setting the fidelity-gap expectation
in copy, not hiding it. Do this as a plain, honest list — not a
gamified score (see §8, item 9, for why a health-score number is
explicitly the wrong model to copy from `reference/audit.md` here).

**Structure.** One row per approximation, grouped by slot/shot, each row
carrying:

- **Fidelity tag** — three states only, each with color + icon + label
  (never color alone): **Exact** (`--rc-green-500`, check icon, usually
  omitted from the list entirely — only approximations and skips need a
  row) / **Approximated** (`--rc-amber-500`, triangle icon — e.g. "Speed
  ramp approximated as 3 linear segments," "Font matched by nearest
  neighbor: Poppins-ExtraBold, 61% confidence") / **Skipped**
  (`--rc-text-tertiary`, dash icon — e.g. "Grade/LUT not applied — v1
  stores grade stats only," directly reflecting `DESIGN_NOTES.md` §8's
  `lut_available: bool = False` default, so the report must say *why*,
  not just *that*, something was skipped).
- **Slot/shot reference** (`slot_id` or shot index, Plex Mono).
- **One-line reason**, evidence-based, in the same direct voice as §1.3.
- **Suggested action**, if any — "Swap this slot" / "Re-render at higher
  resolution" — structurally the same idea as `reference/audit.md`'s
  per-issue "Recommendation" field, adapted from a code-audit context to
  a render-report context.

**Summary line**, plain language, no score: "14 of 16 shots rendered
exactly. 2 approximated. 0 skipped." This is the one place this document
explicitly tells you *not* to copy `reference/audit.md`'s /20 health-score
pattern (see §8 item 9) even though the row-level severity-tag structure
above is directly adapted from it — the row taxonomy transfers, the
score-as-headline-number does not.

### 5.E — `describe_template` human-readable breakdown

**Purpose.** This is, per spec §9.3's own comment, "the 'read the edit'
feature" — the human-facing rendering of the same content an MCP client
gets back from `recut.describe_template`. Design it as a shot list a
working editor would actually read, not a JSON viewer with syntax
highlighting.

**Structure.** Ordered list, one entry per slot (`list_slots` order):
number, small thumbnail/icon, the `human_instruction` sentence as the
headline (per `title-sm`, not buried in body text), requirement tags
below it (same tag component as §5.B), duration/timing as trailing meta
in Plex Mono.

**Evidence disclosure.** Each entry has a collapsed-by-default "Evidence"
expander showing the raw signal that justified the instruction:
contact-sheet thumbnails, the confidence score, and the detector name
(spec §3.6's `evidence` object). This is the single UI pattern that
threads every screen in this document together: spec §4.3's "every
semantic claim must be traceable to a numeric signal" becomes, at the UI
layer, "every UI claim has a one-click path to its evidence." Reuse the
exact same disclosure component in §5.A (shot confidence) and §5.C
(binding score) — one component, defined once in §10, not three
screen-specific variants.

**Agent-facing affordance.** A persistent "Copy as text for your agent"
action at the top of the view, producing the same plain-text/markdown
breakdown an MCP client would receive from the tool call. This makes the
web view double as living documentation of the MCP surface (spec §9.1:
"the agent does the conversational part... for free") rather than a
UI-only reimplementation that can drift from what `describe_template`
actually returns.

---

## 6. Iconography and imagery

**Icon set.** Custom outline glyphs, 2px stroke, drawn on a 24px grid,
geometric with slightly rounded joins (not sharp technical-drawing
corners, not fully rounded "friendly" corners — a middle register that
reads as precise without reading as cold). Monochrome by default
(`--rc-text-secondary`), colored only functionally per the state maps in
§2.5/§5 — never as decoration.

**Required glyph set, literal to the domain, not generic:**
scissors/cut-mark (shot boundary), clapperboard-slate (shot/content),
timecode-clock, metronome-tick (beat), face-detect-box, chevron-whip
(whip pan), crossfade-diamond (dissolve), starburst-tick (flash),
corner-bracket (zoom transition), pause-frame-bracket (freeze frame, not
a generic snowflake), diagonal-speed-arrow (speed ramp), triangle-flag
(low confidence), corner-check (verified/filled), empty-frame (empty
slot), dashed-connector (evidence link).

**The Icon-Tile-Stack ban, named explicitly.** Impeccable's detector
ships a rule literally named `icon-tile-stack` for the single most
common AI-generated-UI tell: a rounded-square icon container sitting
above every card heading. RECUT's slot cards, matcher entries, and
report rows are exactly the kind of repeated-card surface where an
unguided implementation reflexively adds this. **Do not.** Icons in this
system sit inline with their label (leading icon in a button, leading
icon in a badge, a corner glyph on a thumbnail) — never centered in their
own colored tile above a heading.

**Imagery.** The product's own imagery — user thumbnails, contact-sheet
frames, render previews — is the only imagery in the UI. No stock
photography, no illustrated mascot, no abstract blob/gradient art on
empty states. An empty state is: one line-drawn icon (from the set
above) + the direct-voice copy from §1.3. If a screen currently has
nothing real to show (no assets uploaded yet, no jobs run yet), that
absence is communicated with typography and an icon, never with
decorative filler standing in for the missing content.

---

## 7. Motion and animation

RECUT is a tool *about* edit timing and motion; its own UI motion has to
clear the same bar it's measuring in other people's videos, or it
undercuts the product's premise. Per `reference/animate.md`'s Operate-mode
guidance: "motion serves feedback, state, and continuity. Keep routine
transitions fast and do not make users wait through page-load
choreography." That table, applied verbatim to RECUT's own event
vocabulary:

| Duration | RECUT use |
|---|---|
| 100–150ms | Button press, toggle/checkbox confirm (slot bind click) |
| 150–300ms | Slot state transitions — empty→filled crossfade + scale-in of thumbnail, badge color shift |
| 300–500ms | Timeline zoom, panel open/close (matcher drawer sliding in) |
| 500–800ms | **The one authorized focal moment** (below) |

**Easing.** `cubic-bezier(0.16, 1, 0.3, 1)` for confident arrivals. Exit
faster than entrance. **No bounce or elastic easing anywhere** — stated
flatly in `reference/animate.md` as dated, and doubly wrong here: a
bouncy slot-fill animation would visually contradict a product whose
pitch is measured, deterministic precision.

### 7.1 The one focal moment: render-complete reveal

`reference/animate.md` permits exactly one "rehearsed focal sequence" per
surface, when "the surface has earned it" — and explicitly rejects a
generic fade-and-rise or hover-lift as a valid thesis. RECUT's focal
moment: when a render finishes, the progress bar's fill (§7.2) does not
just disappear — over 600ms, the filled bar itself morphs into the output
thumbnail (a FLIP-style shared-element transform, not a cross-dissolve),
which then holds as the render-done preview. This earns its place because
completing a render is the actual payoff moment of the entire product;
nothing else in the UI gets this treatment, which is what keeps it
special rather than diluted across every state change.

### 7.2 Analyzing / render-in-progress: the signature motion identity

Both `analyze_video` and `render` are staged, asynchronous jobs (spec
§9.3/§9.4: async by design, `get_job` returns `stage`). The progress
treatment must show real stages, not a generic spinner:

- A segmented progress bar, one segment per known pipeline stage
  (Ingest → Signal → Semantics → Compile for analysis; encode stages for
  render), each segment labeled with the stage name.
- The **active** segment only carries a moving highlight — a
  `--rc-blue-500` fill with a `--rc-blue-600` sweep animated via gradient
  *position* (not a static gradient fill; see the clarification below),
  looping while that specific stage is running, replaced by a solid
  `--rc-green-500` fill the instant that stage reports done via
  `get_job`.
- This is deliberately not an indeterminate spinner. Spec's own
  architecture already knows what stage is running (§9.3's `stage` field)
  — hiding that behind a generic spinner would throw away information
  the backend already has, and would look exactly like the generic
  "AI tool working…" pattern this document rules out in §8, item 8.

**On the "no gradients" rule and why this doesn't violate it.** §8's
anti-pattern list bans *decorative* gradients (a static purple-to-blue
background wash). The animated sweep above is not that: it is a
functional state indicator whose position encodes real progress, which is
squarely inside `reference/animate.md`'s sanctioned "material and energy"
motion category — "color, gradient position... when the world and
runtime support them." A moving gradient that tells you something is
different from a static gradient that decorates a panel for no reason;
this document bans the second, not the first.

### 7.3 Accessibility

`prefers-reduced-motion: reduce` replaces the scan-line sweep with a
static, solid-color fill at the current proportion plus the stage-name
text label — no information is lost, only the moving highlight. This
matches `reference/audit.md`'s explicit standard: a reduced-motion
alternative must "preserve state change and hierarchy," not just kill the
animation and leave the state ambiguous. The render-complete reveal (§7.1)
degrades to an instant cut to the final state under reduced motion —
still exactly one moment, just not an animated one.

---

## 8. Anti-patterns to avoid, named and sourced

Every entry below cites the specific rule it comes from, and the specific
way a generic AI-built tool UI gets this wrong in a product shaped like
RECUT.

1. **No purple/blue gradients, neon glow, or glassmorphism.**
   [source: `PRODUCT.md` → Anti-references: "Generic AI tool marketing:
   dark mode with purple gradients, neon accents, glassmorphism, glowing
   particles, cyan-on-black."] Applied to RECUT: an Operate-mode utility
   dressed in Persuade-mode marketing chrome undercuts the "deterministic
   tool, not AI vibes" positioning that is the entire product thesis.

2. **No icon-tile-stack.** [source: `README.md` → the named detector
   rule `icon-tile-stack`, "the rounded-square icon tile above every
   heading."] Applied in §6, above — RECUT's card-heavy slot grid and
   matcher list are exactly the surfaces where this reflex fires.

3. **No overused default fonts (Arial, Inter, system defaults).**
   [source: `README.md` → Anti-Patterns list.] Resolved by the explicit
   Plex Sans/Plex Mono choice in §3.1, justified by product fit, not
   picked as "a font that isn't Inter."

4. **No cards nested in cards.** [source: `DESIGN.md` → Do Not: "Do not
   use wide rounded cards or nested cards."] RECUT's slot grid is flat —
   one card level, full stop. The timeline lives entirely outside the
   card system (§4.3) rather than being a "card" wrapping track rows
   wrapping shot blocks.

5. **No gray text on colored backgrounds.** [source: `DESIGN.md` → Do
   Not, and `reference/colorize.md`: "derive secondary text from the
   foreground or surface hue rather than washed-out generic gray."]
   Applied in §2.4's `-fill`/`-text-on-*` split: text on an amber/green/
   red fill uses `--rc-ink` or white per the pairing table, never a
   generic mid-gray dropped on top for "subtlety."

6. **No decorative skeleton shimmer.** Loading-state skeletons (if used
   at all — most RECUT loading states should be the staged progress bar
   in §7.2, not a skeleton) must mirror the real content's geometry
   structurally, the same way Impeccable's own `.ks-skeleton` primitive is
   a structural placeholder, not a decorative shimmer effect layered over
   arbitrary boxes.

7. **No hedging copy.** [source: `PRODUCT.md` → Anti-references: hedging
   language "might," "could," "consider," "perhaps"; `docs/STYLE.md`'s
   prose denylist enforces the same discipline mechanically for
   Impeccable's own copy.] Applied throughout §1.3's voice table — every
   RECUT string that carries a measured value states the value and a
   direct instruction, never a hedge.

8. **No infinite/ambiguous spinners for staged async jobs.** This is the
   single most important anti-pattern for this specific product. [source:
   `reference/animate.md` → Operate-mode guidance: "do not make users
   wait through page-load choreography"; and spec §1's core design rule,
   "the LLM never measures... every semantic claim must be traceable to a
   numeric signal."] A generic spinner during analysis directly
   contradicts a product whose entire premise is a transparent,
   deterministic, stage-by-stage measurement pipeline — see §7.2's
   segmented-progress requirement.

9. **No gamified aggregate score on the render report.** `reference/
   audit.md`'s /20 health-score-with-rating-band format is a genuinely
   good structure for a *code* audit read by a developer looking for
   what to fix next — that's exactly why its row-level severity taxonomy
   (P0–P3, here adapted to Exact/Approximated/Skipped) is reused in
   §5.D. But bolting a single vanity number onto a *render report* read
   by a creator would misrepresent what spec §8.4 asks for: "set this
   expectation in the product copy" honestly, not gamify it. Use the
   plain-language summary line in §5.D instead.

10. **No decorative illustration or mascot art on empty states.**
    [source: §6, Imagery — "no illustrated mascot, no abstract blob/
    gradient art."] Empty states get one functional line icon and direct
    copy; the product's own footage is the only imagery that ever belongs
    in this UI.

---

## 9. Verification protocol (adapted from `reference/audit.md`)

Before any screen in §5 ships, run the equivalent of Impeccable's
"two isolated assessments" pattern (`reference/layout.md`/`typeset.md`/
`colorize.md` all specify this: a design assessment and a mechanical scan,
run independently, synthesized afterward — "a clean scan is a floor, not
proof of good [design]"):

**Design assessment** (answer with rendered evidence, not a bare "yes"):
- Squint test on the slot-grid and matcher: with detail blurred, is
  empty/filled/low-confidence still distinguishable? (`layout.md`)
- Contrast-check every foreground/background pair in §2.3/§2.4 against
  the WCAG table below, on the actual rendered surface, not the spec hex
  values in isolation (`colorize.md`).
- Confirm every color-coded state also carries an icon, shape, or label
  (`colorize.md`'s non-color-cue requirement) — check §2.5's map row by
  row.
- Confirm `prefers-reduced-motion` preserves all state information in
  §7.3.

| Content | WCAG AA minimum |
|---|---|
| Body text | 4.5:1 |
| Large text (`title` and above) | 3:1 |
| Controls, icons, focus indicators | 3:1 |

**RECUT UI quality gate** (adapted from `reference/audit.md`'s five
dimensions and P0–P3 severity, scored per screen before ship):

| # | Dimension | What "4/4" means here |
|---|---|---|
| 1 | Accessibility | WCAG AA on every state in §2.5, reduced-motion alternative present, keyboard path through matcher override control |
| 2 | Performance | Timeline scroll/zoom stays smooth with 100+ shot blocks; no layout thrash on slot-grid state changes |
| 3 | Theming | Every color is a token from §2, no hard-coded hex in component code, dark/light both fully composed (not inverted) |
| 4 | Responsive | Matcher two-pane collapses to a single reachable flow below the 1440px design width; touch targets ≥44px for local-app touch input |
| 5 | Implementation integrity | Every claim rendered (confidence %, approximation reason) traces to a real field in the spec's schemas (§3.6, §5.1) — nothing invented for the UI that isn't in the data |

Severity for findings: **P0** blocks (e.g., a bound slot with no visible
override control — a direct spec §6 violation); **P1** major (contrast
failure on a state color); **P2** minor; **P3** polish. Same bands
`reference/audit.md` uses for code audits, reused here for UI audits.

---

## 10. Component registry and screen routing

Single source of truth for every reusable primitive, named once — per the
ai-agent-foundation-template's `skills.md` convention (one inventory, not
scattered per-screen re-declarations).

### 10.1 Component registry

| Component | States | Defined in |
|---|---|---|
| `Button` | primary (amber fill), secondary (outline), destructive (red), disabled | §2, §4.2 |
| `Badge` | ready (green), flag (amber), error (red), neutral | §2.5, §2.6 |
| `Tag` | neutral requirement/role tag | §5.A, §5.B |
| `SlotCard` | empty / filled / low-confidence-filled | §5.B |
| `ShotBlock` | default / low-confidence | §5.A |
| `TextLayerChip` | per-role icon variants | §5.A |
| `EvidenceDisclosure` | collapsed / expanded | §5.E (reused in §5.A, §5.C) |
| `StagedProgressBar` | per-stage segments, active-sweep, done | §7.2 |
| `ReportRow` | exact (omitted) / approximated / skipped | §5.D |
| `BeatTick` | unlocked / locked (with offset label) | §5.A |
| `TransitionGlyph` | cut / dissolve / whip / flash / zoom, default / low-confidence | §5.A, §6 |

### 10.2 Screen → component routing table

| Screen | Components used | Primary tokens |
|---|---|---|
| Edit Trace viewer (§5.A) | `ShotBlock`, `TextLayerChip`, `BeatTick`, `TransitionGlyph`, `EvidenceDisclosure` | `--rc-surface-1/2`, `--rc-amber-500`, `--rc-green-500`, `micro`/mono scale |
| Template slot-grid (§5.B) | `SlotCard`, `Tag`, `Badge` | `--rc-green-500`, `--rc-amber-500`, `--rc-border` (dashed) |
| Asset matcher (§5.C) | `SlotCard` (bound states), `Button` (Change), `Badge` (banner) | `--rc-amber-500`, persistent-banner pattern |
| Render report (§5.D) | `ReportRow`, `Badge` | `--rc-green-500`/`--rc-amber-500`/`--rc-text-tertiary`, `body` scale |
| `describe_template` breakdown (§5.E) | `EvidenceDisclosure`, `Tag`, `Button` (Copy-as-text) | `body`/`title-sm` scale, `--rc-surface-1` |

### 10.3 Token source of truth

`web/styles/recut-tokens.css` does not exist yet; creating it (as
`:root` custom properties matching §2–§4 exactly, authored in `oklch()`
per `reference/colorize.md`) is the first implementation task this
document implies. This markdown file's frontmatter and §2–§4 tables must
be updated together with that CSS file going forward, the same
mirror-and-update-together discipline `DESIGN.md`'s own header comment
states for its relationship to `kinpaku-tokens.css`.

---

## 11. Decision record

Append future design decisions here as timestamped entries, per the
ai-agent-foundation-template `claude.md` convention: "any architectural
change must be appended to this file under a timestamped heading." Do not
edit past entries; add new ones.

### 2026-08-04 — Initial system authored
Palette, type, spacing, motion, and per-screen direction established as
specified above. No prior version to reconcile against.
