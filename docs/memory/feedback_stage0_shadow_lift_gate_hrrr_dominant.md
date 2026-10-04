---
name: feedback-stage0-shadow-lift-gate-hrrr-dominant
description: "Stage 0 quartile shadow-lift gate is structurally blind on fields where HRRR wins cell-avg in every quartile of every cell (sr, t, likely ws). Move directly to per-obs continuous classifier for those; the per-obs oracle gap is real (10-30% MAE) but no bin-picker can extract it."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ea23724d-936e-4dce-9950-f73f42a59c8e
  modified: 2026-09-20T11:54:30.086Z
---

# Rule

For any per-obs L1-selector Stage 0 (`l1_selector_<axis>_stage0.py`), the shadow-lift MAE gate only fires when **NBM (or the losing model) wins cell-average in at least one quartile** of at least one cell. The gate is min(mae_H, mae_N) per quartile weighted by n — if HRRR wins every quartile at cell-avg, shadow_lift ≡ 0 by construction regardless of how strong the per-obs win-rate spread is.

**Empirically stratified:**
- **Cell-avg mixed fields** (ch, wg, cc, wd, h, dp): NBM wins cell-avg in ≥1 quartile of ≥1 cell → Stage 0 shadow-lift gate works, ims promoted 18 cells on 09-19.
- **HRRR-dominant fields** (sr, t, and by prediction ws): HRRR wins cell-avg in *every* quartile of *every* cell → shadow_lift=+0.00% pooled across the whole Stage 0 table.
  - Confirmed for sr 09-20 (further confounded by [[project_sr_unit_mismatch]] making NBM mae 300-450 W/m²).
  - Confirmed for t 09-20: mae_H 0.6-3.3 °F, mae_N 3.1-6.8 °F across every cell.
  - Per-obs oracle gap on these fields is 10-30% of MAE (t/sea_breeze/24-47h: 30.7%, t/calm/24-47h: 26.9%, t/sw_flow/24-47h: 25.4%) — real and large, but unreachable by any quartile-bin picker.

**Why:** the shadow-picker mimics what the live L1 selector could do if given only a quartile bucket to route on. A quartile is still a cell — its winner is cell-avg-min. So the ceiling of any Stage-0-quartile picker is `always_min(cell-avg per quartile)`. When one model dominates cell-avg universally, that ceiling equals always-that-model, i.e. what the live selector already does.

**How to apply:**
1. Before proposing "try axis X on field Y" for sr/t/ws, check whether NBM ever wins cell-avg on Y in any (regime, band) quartile. If never → the Stage 0 shadow-lift gate cannot fire on Y regardless of axis X. Don't rediscover this by iterating axes.
2. For these fields, skip Stage 0 quartile picker and build Stage 1 v2 (per-obs classifier): logistic-on-continuous-features per (regime, band) with target = `1[mae_N < mae_H]` and features = `[xr_spread, ims, cluster_spread, state_fc-obs, hour_local, ...]`. Gate on held-out MAE lift over always-HRRR at strict halves-stability (test ≥ 3%, test ≥ 0.5× train).
3. When narrating the L1 selector program, treat HRRR-dominant fields as a **separate track** from ims-promoted fields. Not the same pipeline stage — they need a different first stage (continuous classifier, not quartile picker).

**Related:** [[project_l1_selector_per_obs_axes]] documents the H-win-rate spreads on sr and t that this rule explains why we can't act on. Stage 1 sweep of the ims-promoted 18 cells (ch/wg/cc/wd/dp) is unaffected by this — those cells were selected precisely because NBM wins cell-avg in ≥1 quartile.
