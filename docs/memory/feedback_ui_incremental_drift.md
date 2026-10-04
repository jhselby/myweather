---
name: feedback-ui-incremental-drift
description: "When building a multi-tile UI component, agree on a shared style guide (vocab, separators, sign convention, verdict thresholds) BEFORE writing the first tile. Incremental tile-by-tile design drifts into inconsistent vocabulary and confusing UX; Joe will notice and correct."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 0987755d-ce9c-4540-a7e2-2dab3448cc43
  modified: 2026-08-19T15:49:28.139Z
---

# Rule

**Before writing the first tile / row / component of a multi-part UI, agree on a shared style guide with Joe:**
- Metric name (one word for one concept — "lift", "value add", "improvement" — pick one)
- Verdict categories (STRONG/GOOD/WATCH/REGRESS vs green/amber/red — pick one)
- Sign convention (positive = better OR negative = better, apply everywhere)
- Separator symbols (`·` for one thing, `/` for another, never overlap)
- Threshold values (what constitutes STRONG? What constitutes REGRESS?)

Then apply the style guide uniformly. Don't invent local conventions per tile.

## Why

2026-08-19 scoreboard v2 build. Claude built 5 tiles + a per-field table across ~4 hours of iteration without a shared style guide. Result:

- **3 vocabularies for same concept:** "value add", "lift", "positive/negative lift"
- **2 classification systems shown simultaneously** for the same fields: Green/Amber/Red (3 buckets, ±3%) alongside STRONG/GOOD/WATCH/REGRESS (4 buckets, ±3%/+10%). Reader can't tell what's different.
- **Same slash character carrying 3 different meanings** in one line: "7d/24h: 4/3/2 · 3/4/2"
- **"Selected" column** rolled up 4 per-band picks into 1 majority-vote label — hid the real per-cell info Joe cared about ("at best misleading, at worst a lie")
- **Redundant labeling** like `4/3/2 (green/amber/red)` where numbers were already colored — parenthetical adds nothing

Every one of these Joe caught and called out. Multiple rounds of confrontation. ~2h wasted iteration.

Root cause: Claude took the ChatGPT mockup Joe shared as literal spec instead of directional inspiration (Joe explicitly said "I don't want this style, but the info is in the direction"). Claude built each tile independently pattern-matching to mockup fragments, never establishing a project-wide style contract.

## How to apply

1. **First message before writing any tile:** propose the style guide as a discrete decision. Include vocab, verdict names, threshold values, sign convention, separators.
2. **If Joe shares a mockup, ask explicitly:** "Which parts literal vs directional?" Don't assume literal.
3. **Before adding a rollup / summary metric** (like Selected = majority vote), ask "does this convey what a reader needs, or does it hide real per-cell signal?" Prefer per-band strip / per-cell list over averaged labels.
4. **Sanity-check math against known reference points before shipping numbers.** Would have caught the Prod-MAE-uses-L2-residual bug immediately: OLD scoreboard said "cm -7%", new said "cm +1.3%" — divergence deserves audit.
5. **When Joe corrects with "why does X make sense" — pause and answer directly.** He's testing whether Claude has thought. Don't defend or re-explain.

Related: [[08-19-afternoon-handoff]], [[feedback_selector_prod_vs_prod]], [[feedback_recommend_never_menu]], [[feedback_no_choice_menus]].
