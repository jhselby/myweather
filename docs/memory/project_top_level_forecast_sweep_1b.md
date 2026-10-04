---
name: top-level-forecast-sweep-1b
description: "08-09 chunk 1b of code+logic audit — 5 analysis scripts fixed to stop treating top-level `forecast` as L1 or Production. Reruns pending user go-ahead (may shift live-gate verdicts)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8936b8c9-2577-4ecc-9d6b-6658da634b60
  modified: 2026-08-09T13:39:56.854Z
---

Follow-up to `[[project_top_level_forecast_sweep]]` and `[[feedback_top_level_forecast_is_l2]]`. Chunk 1b of 08-09 code+logic audit.

**Fixed (uncommitted, working tree):**
- `analysis/h_wd_persistence_gate_stage1.py:142` — was `fc = r.get("forecast")`, script intent is L1 baseline. Now `forecast_l1` w/ top-level fallback. Impacts 07-27 wdp flip decision retroactively (~24% of wd rows had wrong `fc`).
- `analysis/h_wd_persistence_gate_stage2.py:162` — same fix.
- `analysis/h_l3_asymmetric_stage1.py:119,170` — was `fc = r.get("forecast")` for fc_bin quantile cuts and err_l1. Fields: wg, ws, cm. For wg/ws top-level differs from L1 on 25-26% of rows so bin thresholds shift.
- `analysis/h_wg_residual_persistence_stage1.py:70` — was `fc_prod = r.get("forecast")`. Now applied_layer reconstruction w/ L4 fallback. wg has L3 hidden on ~74% of rows — largest expected verdict shift.
- `analysis/h_dp_residual_persistence_stage1.py:74` — same pattern. dp's L2 IS applied 86% so smaller effect but non-zero (L4 fires ~3%).

**Skipped as low-impact (Group C — top-level used only as fallback for missing forecast_l3):**
- `analysis/h_wg_l3_regression_stage1.py:134`, `h_wg_l3_regression.py:119`, `h_ws_l3_regression_stage1.py:134`. `fc` only used to null-fill `fc_l3` when missing; actual scoring uses `err_l3`/`err_l2`/`err_pers`.

**Skipped as verified-safe:**
- `analysis/anomaly_detector.py` — uses top-level for both baseline AND recent windows; drift signal is internally consistent even at L2-semantic (measures "did L2 baseline shift" which is still a valid anomaly signal).
- `analysis/pop_calibration.py` — pp-only; verified L1-only end-to-end (`[[project_pp_is_l1_only_verified]]`).
- `analysis/pp_brier_reliability.py`, `pp_brier_decomposition.py`, `h_pp_bias_persistence_stage0.py` — same pp verification.

**Next action (needs user):** rerun the 5 fixed scripts and compare verdicts against last committed curated JSONs. Any SHIP/HOLD/FLIP delta → new gate decision. Direction of biggest concern: wg residual persistence and wd stage1 (07-27 flip could look different in corrected metric).

**Why:** all these fixes flow from the invariant `top-level forecast == forecast_l2` (verified 08-09 on 21,494 rows per field). Silent bug class shared with `[[feedback_shadow_write_applied_layer_trap]]`, `[[feedback_l1_only_field_routing_trap]]`, `[[feedback_pair_log_error_field]]`, and the collector-side wd applied_layer stamp fix in `[[project_wd_applied_layer_stamp_fix]]`.
