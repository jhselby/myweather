---
name: feedback-check-own-arithmetic
description: "When presenting a computed number derived from a visible column of data (means, medians, counts, deltas), verify the arithmetic matches the underlying values before showing them. The user reads the same column and will catch an off number instantly — being behind on arithmetic destroys credibility fast."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4497b339-2efa-4cc6-a9d8-ca9e374ecf4a
  modified: 2026-08-09T11:19:21.509Z
---

Before presenting any computed number (mean, median, count, percentage, delta) derived from a column of data the user can see, verify:

1. **The number matches the visible data.** Do a quick reality-check: if you say "X drags the mean toward Y," compute a rough version to confirm X actually contributes to the calculation. If you claim "half the fields have property Z," count them.

2. **The claim matches the source of truth.** When the number comes from a script/dashboard, read the actual code that computes it — do not infer from adjacent code. The scoreboard median incident happened because I assumed pp was in `scoredRows` when the code explicitly skips brierFields at row-build time (`if (brierFields.has(fieldKey)) continue;`). One glance at line 2919 would have caught it.

3. **The interpretation matches the direction.** Sign errors and "drags down/up" mismatches are worse than wrong numbers because they invert the conclusion. Example: in MAE %-vs-raw, negative is good; a big win like -57% doesn't "drag the mean down" in any pejorative sense — it improves the mean.

**Why:** 2026-08-09 session — user asked "what's pulling down our MAE median?" I listed 10 fields and pointed at pp (+0.0%) as one of three flat-zero fields pulling the median toward -0.8%. User replied: "besides pp ALL of the fields have a better number than -0.8%" — because pp WASN'T in the median calc at all (routed to brierRows). Correct answer: pa/pr/cl were the three +0.0% fields dragging the median. User's frame: "I shouldn't have to look at a column of numbers and be able to see right away that your calculation is off. You should be ahead of me on that kind of thing, not behind me."

**How to apply:** For any user-facing claim that involves counting, averaging, or "X causes Y in the aggregate":
- If the source is code you have access to, read it once to confirm which rows/fields are included.
- If you list numbers, do the mental arithmetic on those numbers before writing the interpretive sentence. If the interpretive sentence disagrees with the listed numbers, one of them is wrong — pause, don't ship.
- Do not use directional language ("drags down," "pulls up," "hurts the score") without first confirming the sign convention.

Related: `[[feedback_verify_field_is_corrected]]` (same session, different failure — 3-check reflex before proposing correction-stack work) · `[[feedback_measure_before_concluding]]` · `[[feedback_dont_invent_numbers]]` · `[[feedback_search_before_proposing]]` · `[[feedback_check_contamination_before_acting]]`.
