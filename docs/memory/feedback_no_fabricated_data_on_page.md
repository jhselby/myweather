---
name: no-fabricated-data-on-page
description: "Mocking up a page with fake numbers is fine as a design draft, but never write fabricated data into the live/published page. Real, static (with a clear note), or absent — those are the only acceptable states for values the user reads."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1bad34ba-cdca-4f8f-9372-1d79aee9ca3f
  modified: 2026-08-25T22:11:17.316Z
---

Fake numbers on a chart or table are read as data. Joe's eye — anyone's eye — goes straight to the numbers, not to accompanying warning text. A warning next to a chart is invisible to the reading path; even a warning ON the chart doesn't reliably help, because the numbers are what get read. Don't put fabricated numbers in front of the reader. Period.

**Why:** raised 2026-08-25 after v0.6.480 wired the per-field diagnostic table live. Previous state had hand-hardcoded values carried over from an earlier baseline, with a ⚠ warning in the sub-blurb. I initially framed it as "warning wasn't loud enough" — wrong framing. The framing Joe corrected me to: warnings adjacent to numbers do not intercept the reading path. The only fix is to not put invented numbers where numbers get read.

**How to apply:**
- Mockups (design drafts, private previews, Artifacts shown inline, files in scratchpad): fake data fine — it's the whole point of a mockup.
- Live/deployed page or any file being pushed to prod: values must be either (a) real / computed from a live source, or (b) absent — dashes, "—", column dropped, section hidden. That's it. There is no (c) "fake but warned about."
- Do NOT rely on caveats, footers, ⚠ notes, opacity, or grey styling to communicate "these are placeholders." They don't work. The reader reads the number.
- If a section can't ship with real data yet, don't ship its numbers. Ship the shell with dashes, or omit the section.

Related: [[feedback_dont_invent_numbers]] (similar rule for prose/analysis), [[feedback_stated_intent_vs_code_behavior]].
