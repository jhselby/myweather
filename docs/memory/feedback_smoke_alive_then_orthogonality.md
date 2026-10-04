---
name: feedback-smoke-alive-then-orthogonality
description: A SMOKE_ALIVE verdict is necessary but not sufficient for promoting a hypothesis. Always run the orthogonality check against existing live axes before treating a candidate as worth productionizing.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 19e46001-b953-40c1-a522-231781ec1562
---

When a hypothesis returns SMOKE_ALIVE, do NOT treat it as ready for productionization. The SMOKE_ALIVE test is "does ANY (field, band) cell show signal?" — it doesn't distinguish a genuine new signal from a re-discovery of a signal an existing C1 axis already captures.

**Why:** Two consecutive cases in 2026-06 confirmed the pattern:

- **C1g (cc-saturation):** SMOKE_ALIVE → orthogonality vs C1f + cc-saturation returned `69/72 redundant` → killed 2026-06-24.
- **C1d (KBOS-vs-KBVY σ):** SMOKE_ALIVE 2026-06-28 → orthogonality vs C1a + C1e returned `3/4 redundant` (σ signal inverted once C1a was held fixed) → killed 2026-06-29.

In both cases, the smoke test was honest about there being SOME signal — but the signal was the regime-transition signal C1a was already encoding. Promoting on smoke alone would have wired a redundant axis into `c1_confidence_curated_v2.json`, adding noise to the join and to the calibration audit.

**How to apply:**
1. Treat SMOKE_ALIVE as "now write the orthogonality script" — never as "now promote."
2. The orthogonality script must check independence vs **every live C1 axis** (currently C1a, C1e, C1f), not just one. Cells must clear the n floor in the held-fixed subset, which often means the orthogonality check needs more data than the smoke test did.
3. If the orthogonality script returns KILL or MIXED-mostly-redundant, the candidate is dead. Document it in `project_c1_pivot_to_confidence.md` so a future session doesn't waste time reviving it.
4. If orthogonality is INSUFFICIENT (e.g. C1e arm has n=0 cells), accept that as "incomplete" and let the data accumulate — don't promote on the partial result.

**Template scripts:** `analysis/h_pre_front_orthogonality.py` is the canonical structure for orthogonality checks. `analysis/h_cloud_disagreement_orthogonality.py` (built 2026-06-29) is the most recent example and uses Q3-cut binary HIGH/LOW with C1a + C1e held-fixed comparisons.

Related: [[feedback-orthogonality-gate]], [[project-c1-pivot-to-confidence]], [[feedback-hypothesis-promotion-pipeline]].
