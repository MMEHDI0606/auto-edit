# find_similar_template

Use this when the user wants an edit STYLE (pacing, hook type, structure)
rather than reproducing one specific reference video - "find me something
like a fast-cut product reveal" or "I want that talking-head-then-b-roll
thing again."

## Sequence

1. **Search the local library.** Call `search_library(query, filters=None)`
   with keywords drawn from what the user described (e.g. `"hook"`,
   `"reveal"`, `"reaction"` - words that would plausibly appear in a
   slot's `human_instruction`). This searches only templates already
   produced by a previous `analyze_video` call in this environment - there
   is no pre-seeded third-party template library yet, so an empty result
   is a real, expected possibility, not a bug. If it comes back empty, say
   so plainly and offer `recreate_this_edit` instead (the user picking a
   fresh reference video to analyze).

2. **Narrow down with the user.** `search_library` returns a list of
   `{template_id, slot_count}` - not enough on its own to pick from. For
   each promising candidate, call `describe_template(template_id)` and
   show the user the resulting plain-language breakdown so they can
   recognize which one (if any) matches what they had in mind. Don't just
   list template_ids at the user - ids mean nothing to a human, the
   description is the actual product surface here.

3. **Once the user picks one,** continue exactly like
   `recreate_this_edit` from its step 5 onward (register the user's
   footage, match, review, optionally `adjust_template` for a style tweak,
   bind, preview, render, deliver).

## A note on scope

Don't try to rank or fuzzy-match candidates yourself beyond what
`search_library`'s substring match already does - if the search feels too
narrow or too broad, that's feedback worth surfacing to whoever's
iterating on this tool's matching logic, not something to work around by
inventing your own scoring in the conversation. If several candidates
come back, presenting 2-3 of the best-described ones for the user to
choose between is better than dumping every result.
