---
name: feedback-fresh-fire-lucky-baseline-artifact
description: "Regression sentry's 3d vs 7d ratio can FRESH FIRE when a single anomalously-good day sits inside the 7d window but outside the 3d window. Check daily baseline before hunting causes."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 40f9e9ba-be00-41a3-9599-054163520bc8
  modified: 2026-09-17T12:31:43.116Z
---

The regression sentry compares 3d MAE vs 7d MAE and flags FRESH FIRE at ≥+15%. This ratio fires false-positive when **one atypically-easy forecast day is inside the 7d window but outside the 3d window** — the 7d mean gets pulled down, the 3d looks bad by comparison, and neither window is actually a regression.

**Rule:** on any FRESH FIRE, plot the field's daily raw MAE for the last 10-14 days FIRST. If one day inside the 7d-but-outside-3d segment is 30%+ below neighbors, the fire is a baseline artifact — no action, and the sentry will heal on its own when that day rolls off the 7d window (7 days later).

**Why:** Before this shortcut, a false-positive fire would lead into a full publisher/routing/regime dig. The fix is a one-column table lookup that costs 30 seconds and saves an hour of chasing nothing.

**How to apply:**
1. Pull `analysis/output/mae_over_time.json` → `series.{field}.raw` (or `raw_nbm` if the field routes to NBM at the affected leads) for last 14 days.
2. Eyeball the daily sequence. If one day inside days-7-to-3-ago is ≥30% below neighbors, flag as baseline artifact and clock-watch to auto-heal.
3. Also check the same field's `prod` daily sequence — if prod tracks raw's dip, it's a genuinely easy forecast day, not a data glitch. Both are baseline artifacts.

**Case study 2026-09-17:** t FRESH FIRE 3d +18.9% / 7d +5.6% (n=2,551). Daily raw NBM MAE for t:
- 09-12: 1.578 · 09-13: 1.342 · **09-14: 0.887** · 09-15: 1.476 · 09-16: 1.632 · 09-17: 2.011
- 09-14 was ~40% below neighbors. 3d window (09-15/16/17) excludes it, 7d includes it. Same NBM aggregate performance as 09-12/13; only 09-14 broke pattern. False alarm. Confirmed by selector-picks being stable (HRRR ~48% / NBM ~44% every day). Sentry expected to auto-heal by 09-21 when 09-14 rolls off 7d.

Related: [[feedback_fresh_routing_loss_diagnosis]] · [[feedback_prod_real_vs_replay_divergence]] · [[feedback_dont_over_gate]].
