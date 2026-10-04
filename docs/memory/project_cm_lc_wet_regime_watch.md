---
name: cm-lc-wet-regime-watch
description: "cm Lc hurts in se_flow/pre_frontal/frontal, helps in nw_flow. Do NOT _FIELD_SKIP cm; wait for recent-bias gate walker to clear. Re-escalate to surgical _CELL_SKIP only if the wet-regime damage repeats on a distinct future stretch."
metadata: 
  node_type: memory
  type: project
  originSessionId: 32832742-5efb-4b02-a23b-3cd645f9da4d
  modified: 2026-08-17T11:56:52.490Z
---

# cm Lc wet-regime watch (opened 2026-08-17)

**Trigger:** 08-17 morning triage. cm real production MAE (reconstructed from `error_{applied_layer}`) was 29.0 last 24h vs 14.0 prev 24h (+107%). L2 alone was 23.8 → Lc contributed ~5pt of average MAE damage across the 402 Lc-fired rows.

Regime breakdown (last 24h prod MAE, cm):

| regime | n | raw | post-Lc | Lc Δ |
|---|---|---|---|---|
| se_flow | 606 | 26.3 | 33.4 | **+7** |
| pre_frontal | 254 | 28.4 | 35.4 | **+7** |
| frontal | 86 | 33.6 | 38.8 | **+5** |
| nw_flow | 69 | 4.4 | 1.3 | **−3** (helps) |
| sea_breeze | 78 | 19.2 | 17.9 | −1 |
| ne_flow / calm | 85 | ~3 | ~3 | 0 |

Lc for cm was fit on an nw_flow-heavy history. In wet regimes the fit inverts.

**Why:** Joe explicitly asked to wait rather than ship a bandage. Reasoning: `_FIELD_SKIP` cm would strand it the way cl has been stranded since 2026-07-30 (still dead, no self-heal path once Lc data stops flowing). The `lc_recent_bias_gate` mechanism is the correct long-term fix and cm's per-field walker (`BUILDING 5/7 days` at 08-17, churning ch/cm/cl set) needs continued Lc data to eventually clear.

**How to apply:**
- Do NOT add cm to `cloud_saturation_correction.py::_FIELD_SKIP` reflexively when a single wet-regime day looks bad. Regime shift back to nw_flow restores Lc's win.
- Do NOT add hand-typed `_CELL_SKIP` tuples yet — same anti-scar-tissue reasoning as [[project_chp_cell_skip_to_dynamic_gate]] item 6 of pipeline-to-good.
- **Re-escalate to surgical `(cm, regime, bin)` in `_CELL_SKIP`** only if a **second distinct wet stretch** (not the same one continuing) reproduces the se_flow/pre_frontal damage. One incident = raw regime shift; two = Lc fit itself is broken for those regimes.
- Watch: recompute cm real prod MAE from `error_{applied_layer}` on the next se_flow/pre_frontal dominant 24h and compare to today's 43.9 (l6-stamped rows).

**Related pattern trap:** original morning triage used `error` field as production, which is L2 by design ([[feedback_top_level_forecast_is_l2]]). Real prod MAE was double what the L2 residual showed. The digest's `anomaly_detector` similarly reported cm CLEAN today — probably reading L2 too. Sweep candidate: any digest analysis that treats `error` as production. Follow-on workstream, not urgent today.

## Related
- [[project_lc_regime_conditional]] — the standing item this watch feeds into
- [[project_lc_cl_unskip_investigation]] — the cl trap we're avoiding
- [[feedback_top_level_forecast_is_l2]] — the analysis correction that changed the diagnosis
- [[project_plan_pipeline_to_good]] — item 6, anti-scar-tissue rationale
