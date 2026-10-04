---
name: section-cruft-accretion
description: "Individual UI improvements can compose into a regression. Each change to a section may be defensible in isolation; cumulative effect isn't. When a debug-page section has accumulated ~5+ changes across recent months, do a 'read it fresh' pass and ask if the SECTION still earns its screen real estate — not just whether the individual pieces are still correct. Codified 07-13 after Joe surfaced that the Accuracy section had become 'a lot less useful' post-v0.6.340 RMSE+bias companion tables. Two individually-correct decisions (only-applied-layers filter + thick Production line) combined to gut the chart's remaining value; redesign killed the chart entirely (v0.6.350)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d1c5631e-fa3f-4890-b497-9e86b29ebc91
---

## The rule

When a debug-page section has accumulated ~5+ changes across recent months, do a **read-it-fresh** pass. Ask if the SECTION still earns its screen real estate, not whether each individual piece is still correct.

**Why:** individual UI improvements can compose into a regression. Each recent change may be defensible in isolation. The cumulative shape isn't — cruft accretes silently while ship-by-ship review only catches per-change regressions.

**How to apply:**
- Trigger: any section that's had ≥5 ships touch it in the last 4-6 weeks, OR the moment Joe says a section "seems less useful."
- Read the section as if you'd never seen it. What is a first-time reader looking for? Does the section answer that in ≤10 seconds?
- Ask: does each block earn its space against the block next to it? If two blocks answer overlapping questions, one dies.
- Killing established UI is scary but usually the right move once the answer is "no." A chart on the page for months is not sacred — the question is whether it earns space against what's next to it, not whether it should exist in some abstract sense.

## The trigger case (07-13, v0.6.350)

**Symptom:** Joe said "the accuracy section on the page has become a lot less useful. Suggest a redesign."

**Diagnosis:**
- v0.6.340 added `_layersFor()` filter dropping inactive layer lines (correct: prior version stacked 4-5 identical lines).
- v0.6.340 also added RMSE + bias companion tables (correct: MAE-only view missed occasional big misses + systematic drift).
- Somewhere in there, a thick Production line was added (correct: user-visible answer should stand out).

**Cumulative effect:** the chart's original value-add was per-layer visual contribution. The filter removed most of the layers. The thick line ate what was left. The three tables per card became a wall of vertical space. Net: less useful section than the version 6 weeks earlier.

**Fix:** killed the chart entirely, folded three tables into one combined band × metric table. Half the vertical footprint per card, higher signal density.

## Anti-pattern to avoid

Treating "the current section is a superset of every prior version" as automatically better. Each ship added information. None removed it. Additive-only UI evolution is how sections turn into walls of noise.

## Related

- [[07-13-session]] — the session where this was codified.
- [[feedback-hypothesis-promotion-pipeline]] — the same "each stage is individually correct" logic applies to hypothesis promotion.
- [[feedback-do-it-right]] — killing UI cleanly is preferable to hedging with a shrunken-but-still-there chart.
