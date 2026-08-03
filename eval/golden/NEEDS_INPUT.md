# Blocked on real video input

Unit 0.3 / Unit 1.19 require 3 (then 20+) hand-annotated real short-form
videos per `INSTRUCTIONS.md`. This cannot be fabricated by an agent:

- Ground truth must come from a human scrubbing a real video frame-by-frame
  ("there is no shortcut here" - INSTRUCTIONS.md Unit 0.3).
- Bulk/automated scraping of IG/TikTok is explicitly out of scope
  (RECUT_SPEC.md sec 8.1, DESIGN_NOTES.md "Legal posture") - only
  user-uploaded files or user-authorized single-URL pulls are supported.

**What's needed from you to unblock Unit 0.3 / the Phase 1 gate (Unit 1.19):**
1. 3 short-form videos (any genre, ideally spanning talking-head/product/
   dance/text-tutorial/b-roll) you have the rights to use - either local
   files or URLs you're authorized to pull - dropped somewhere I can read
   them (e.g. a local folder path), plus
2. Hand-verified ground truth for each: cut timestamps + type, text layer
   strings/timing, approximate tempo - or your go-ahead for me to
   hand-label them myself by scrubbing frame-by-frame once files exist.

**What's NOT blocked:** every Phase 1 unit's own unit tests use synthetic,
license-free fixtures (see `tests/fixtures/make_synthetic_clip.py` and
per-unit synthetic test cases in `tests/signals/`) and do not require real
video. Implementation proceeds without waiting on this - only the final
Unit 1.19 gate numbers (cut-boundary F1 >= 90%, text IoU >= 85% over a real
20-video set) are blocked until real footage is supplied.
