---
name: divergence-claim-mismatch
description: "Divergence report claims must be sourced from the same signal the live gate uses, not from a candidate-refinement script that happens to share a name."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d0ce8e13-443e-4221-9625-a6ecbc9e587f
  modified: 2026-07-20T12:18:48.331Z
---

# Divergence report claim source must match the live gate

Rule: when a specialist has BOTH a live gate history (Fitter emits
SHIP/HOLD per cycle to `<layer>_gate_history.json`) AND a candidate
sibling script (`l5_solar_analysis.py`, testing a refinement that never
shipped), the divergence-report claim for the live flag must route
through the LIVE gate history, not the candidate script's verdict.

**Why:** the divergence report shows "READY to change production" when
the claim disagrees with production and a 7-day gate clears. If the
claim is sourced from a candidate-refinement script, that script's HOLD
verdict (which means "don't ship the candidate") gets falsely rendered
as "retire the live layer." This happened for LSR_ENABLED for months
(2026-06-28 through 2026-07-20): live L5 gate was 100% SHIP but the
divergence table said READY-to-flip-off because `l5_solar_analysis`
verdict was HOLD (candidate 3/8 regimes improving, need 5).

**How to apply:**
- Before adding a new specialist to the divergence claim map (in
  `analysis/runlog/claims.py` and `build_executive_summary.py`
  `_claim_source`), identify which artifact carries the live-gate signal.
- If it's a URL/cache-based history (like `l5_gate_history.json`),
  write a helper that reads the cache and derives True/False from a
  day-rollup — mirror the trajectory logic `divergence_report.py`
  already uses in its rendering path.
- Don't source live-flag claims from Stage 0 / candidate scripts unless
  those scripts operate on the LIVE gate's signals.
- Verify by running `divergence_report.py` after the change and
  confirming AGREE status on flags whose live gate is passing.
