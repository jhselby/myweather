---
name: pooled-n-time-thin
description: A pooled read with large n can still be a time-thin single-window artifact. Always report the calendar span of the corpus and check halves before recommending action.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 73429c93-7451-4383-be7a-18cb78ea6325
  modified: 2026-07-29T13:27:41.561Z
---

# Pooled n-large ≠ statistically robust — check calendar span

**Rule:** Before recommending action on a pooled cross-cut (regime × lead, halves, etc.), report the **calendar span** of the qualifying data, not just the row count. A pooled read of "20k rows, 6 WIN cells at n≥200" sounds strong until you notice all 20k rows come from a 5-day window — at which point every "WIN" is fitting one specific weather pattern.

**Why:** 2026-07-29 pr L2 retro. I ran `analysis/pr_l2_regime_lead_retro.py` on ~20k L2-applied pair-log rows, found 6 WIN cells with strong effect sizes (up to +26.7%) and confidently framed the result as "6 WIN cells with real physical stories" — implying weeks of retro evidence. Joe asked whether we had enough to enable now. My initial answer waffled toward yes-with-caveats. Then he pushed on confidence.

Halves-verification revealed the actual corpus was only **~5 days** (06-29 → 07-03, with the 07-01 kill mid-window). Jaccard(A, B) = 0.00. Four cells flipped sign 40-45 points between the two 3-day halves. Two of the strongest pooled effects couldn't even be halves-tested (sample concentrated on one side of the median). The pooled result was fitting ~5 days of specific weather, not stable regime physics.

Had we shipped on the pooled read alone, we would have re-enabled a correction based on 5 days of weather-noise fitting. The 07-01 pooled kill would have been reversed by another pooled read — same class of decision that got flagged in [[feedback_calm_gate_wrong_intervention]] and [[feedback_regime_gate_first]], now with the added irony of it being the *reverse* mistake.

**How to apply:**
1. **Every cross-cut script must report the calendar span of the qualifying data**, not just n. Add first-obs-time / last-obs-time / span-in-days lines to the header output. Retrofit older scripts as they come up in ship decisions.
2. **Halves-verified is the discipline for L-layer ship decisions**, not just specialists (dpbp/wsbp/pp Platt already do this). L2 / L3 / L4 re-enables and drops need the same treatment before Stage 1 verdict.
3. **When Joe asks "confident enough to ship now?" the honest answer requires halves.** If halves haven't been run, the answer is "not yet, run halves first" — never "yes based on pooled." This is [[feedback_measure_before_concluding]]: the measurement is 1 script-edit away.
4. **Sample-concentration check:** if a "pooled WIN" cell fails the n≥floor test in either half, it means the sample is one-sided in time — treat as strictly weaker than a cell that passes n-floor in both halves regardless of pooled Δ%.

Related: [[feedback_streak_walker_robustness]] (Jaccard ≥ 0.8 standard for cell overlap in streak walkers) is the sibling rule for streak infra; this rule extends the same discipline to cross-cut ship gates.
