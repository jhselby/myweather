---
name: chooser-lift-negative-is-bug
description: "Chooser lift losing on any field pooled is a diagnostic signal (fit staleness / gate / band mismatch), NOT \"wait it out for NBM to catch up.\""
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a5f6d3e2-3ab8-43f2-8697-4381ee8e9c0b
  modified: 2026-08-22T11:20:18.889Z
---

A working L1 chooser trained on Prod MAE per (field, band) with a lift gate should read chooser_vs_prod_pct ≥ 0 pooled on every field, almost by definition — at every cell it's picking the historically-better cascade.

**Why:** Rule stated by Joe 2026-08-22: "the chooser has to be either winning or flat on every field or it's not working right."

**How to apply:** When the L1 chooser lift tile ([[08-22-session]] Prod-vs-Prod, v0.6.466) shows a field in "losing," do NOT respond with "NBM Prod will catch up." Treat it as a diagnostic and investigate one of three culprits:

1. **Fit window vs eval window mismatch** — fitter uses 30d, tile shows 7d. If NBM Prod is trending better fast (specialists shipping), 30d fit averages in weaker early NBM performance and picks HRRR while 7d eval sees the newer NBM and shows we missed. Fix: tighten fit to 14d or add recency weighting.
2. **Gate too conservative** — min_lift=3.0% means a cell where NBM is 2% better stays on HRRR. Multiple such cells pool to slightly negative field-level lift. Fix: drop threshold or use two-sided rule.
3. **Bands mask sub-range wins** — 4-band cuts (0-5, 6-11, 12-23, 24-47) can mix a HRRR-wins sub-range with an NBM-wins sub-range inside one band. Fix: finer bands or per-lead-hour fit.

See [[project_chooser_fit_diagnostics]] for the open TODO on t/h/wd.

Related: [[feedback_selector_prod_vs_prod]] (never compare raws when judging selector quality).
