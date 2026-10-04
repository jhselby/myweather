---
name: yellow-band-2pct
description: "Scoreboard yellow band is ±2%, not ±3%. Matches empirical 1σ SE of a 7d median lift."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ce47e518-fc0a-42dd-8729-c179ac0dae40
  modified: 2026-08-27T14:10:14.507Z
---

Scoreboard tile color rule: green ≥ +2%, red ≤ −2%, yellow between. Shipped v0.6.510 (2026-08-27) after Joe asked "why 3%?" and answer was "no reason — matched other watchdog thresholds by convention."

**Why:** Empirical 1σ SE of a 7d median lift is ~2% for well-behaved fields (t: MAE ~5°F, n~5,000 paired obs, SE ≈ √2 × 0.07/5 ≈ 2%). ±3% was ~1.5σ (over-conservative — real drift stayed yellow longer than it should). ±2% ≈ 1σ.

**How to apply:** When adding new lift-based color rules, use ±2% by default and don't invent a new number. Locations: `analysis/scoreboard_v2.py` (`VERDICT_GOOD_LIFT`/`VERDICT_REGRESS_LIFT`) and `corrections_debug.html` (two `_cls` fns + WFL bucket splitter + inline lift cls). Related derived rules (Health tile's `|lift| < 3 = LOW confidence` etc.) still use their original thresholds — those are separate calibrations.

Trade-off accepted: more color churn on noisy fields (pp, sr, cc under regime shifts) in exchange for earlier signal on real drift.
