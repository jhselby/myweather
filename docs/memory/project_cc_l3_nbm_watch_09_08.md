---
name: project-cc-l3-nbm-watch-09-08
description: "09-08 late-evening cc scoreboard REGRESS diagnosis — l3_nbm hurts cc vs raw_nbm in 24h (prod 24.37 vs raw 21.85, −11.5%), but sentry says CLEAN because marginal help vs l2_nbm is +5pp. 3-day watch, don't ship yet."
metadata: 
  node_type: memory
  type: project
  originSessionId: f4f9924e-0098-4fb2-bee7-03e379adcce9
  modified: 2026-09-08T21:47:58.088Z
---

# cc l3_nbm 24h REGRESS — watch, don't ship (2026-09-08)

Opened 09-08 late-evening. Scoreboard v2 24h shows cc REGRESS: prod_mae=24.37, nbm_raw_mae=21.85, lift_vs_best_public=−11.52%, lift_vs_hrrr=+50.21%. Halves agree (+51/+47). Concentrated in leads 6-11, 12-23, 24-47; 0-5h fine.

## Root of the 24h loss
Pair-log last 24h (n=1223 cc rows, own dump, not sentry):
- raw_nbm 17.28 · l2_nbm 16.86 · **l3_nbm 18.83** · l4_nbm 18.50 (l4 is no-op post v0.6.563).
- l3_nbm burns ~1.5 MAE vs raw_nbm; selector picks NBM so prod inherits it.

## Why sentry says CLEAN — legit disagreement, not bug
Sentry cc.l3_nbm CLEAN, layer_help_pct sustained +3.07 → fresh +4.99 (helping MORE, not less). Sentry compares layer vs **input** (l2_nbm), not vs raw_nbm. In fresh window l2 climbed to 25.2 MAE while l3 climbed to 23.4 — l3's marginal help expanded. But l2 itself has drifted worse than raw, so the whole NBM branch loses to raw despite l3 helping l2. Sentry is doing its job; the scoreboard is measuring a different (user-visible) quantity.

## Why not ship a cc DROP from L3_NBM today
- Signal is 24h only. 7d cc: prod +5.95% lift_vs_best_public (GOOD).
- Sentry disagrees using its intended metric.
- Would also drop the +5% l3-over-l2 help that sentry sees.

**How to apply:** hold. If 3d or 7d scoreboard also flips REGRESS for cc AND sentry's absolute-MAE column shows l3 > raw_nbm on the same window, then DROP cc from L3_NBM_FIELDS is the ship (parallel to h ship 09-05 v0.6.551 and cc-from-l4 ship 09-08 v0.6.563).

**Clock:** revisit 09-11 (walker wire day; also 3d aged out). If still REGRESS, ship.

Related: [[project_09_08_evening_session]] · [[feedback_measure_before_concluding]] · [[feedback_nbm_regression_sentry_semantics]].
