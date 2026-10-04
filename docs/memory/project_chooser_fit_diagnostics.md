---
name: chooser-fit-diagnostics
description: "Open TODO — diagnose why L1 chooser is losing pooled on t/h/wd (Prod-vs-Prod). Per feedback_chooser_lift_negative_is_bug this is a bug signal, not wait-it-out."
metadata: 
  node_type: memory
  type: project
  originSessionId: a5f6d3e2-3ab8-43f2-8697-4381ee8e9c0b
  modified: 2026-08-22T11:20:33.751Z
---

**State 2026-08-22 post-v0.6.466**: L1 chooser lift reads:
- winning: wg (+6.3%), ch (+30.1%), sr (+9.3%)
- flat: ws (−1.2%)
- losing: t (−23.0%), h (−27.1%), wd (−16.1%)

**Why:** Per [[feedback_chooser_lift_negative_is_bug]] a working chooser should read ≥0 on every field pooled. t/h/wd losing means the fitter is picking HRRR at cells where NBM Prod would win pooled over the eval window. Real cost: on Prod MAE at those fields we're leaving lift on the table.

**How to apply:** When picking up this thread, try (in order):

1. Print each cell's fitted `source`, `hrrr_prod_mae`, `nbm_prod_mae`, `lift_pct`, `n` for t/h/wd from `weather_collector/data/l1_selector_table_curated.json`. Which cells are 1-2% NBM-better but stayed HRRR (gate-conservative), which cells are HRRR-better in 30d fit but NBM-better in 7d eval (fit-window staleness)?
2. Re-run `analysis/l1_selector_fit.py` with a 14d window instead of 30d. Compare picks. If the shorter-window fit flips t/h/wd cells to NBM, staleness is confirmed and the fix is either shorten `window_days` or add recency weighting.
3. Check per-lead-hour NBM vs HRRR Prod within the 12-23 and 24-47 bands. If there's a within-band crossover (e.g., NBM wins at 12-18h but loses at 19-23h), the band shape needs finer cuts.
4. Consider dropping `min_lift_pct` from 3.0 to 1.0 or 0.0 (two-sided rule). See what pooled chooser lift becomes on a re-fit.

Deferred to a future session — not blocking anything today. Related: [[08-22-session]], [[feedback_selector_prod_vs_prod]].
