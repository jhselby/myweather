---
name: pp-is-l1-only-verified
description: "pp field is L1-only end-to-end in production (verified 2026-08-09). Top-level `forecast` == `forecast_l1` == `forecast_l2` and `applied_layer` == 'l1' for 100% of rows. Analysis scripts reading top-level `forecast` for pp are scoring correct baseline."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8936b8c9-2577-4ecc-9d6b-6658da634b60
  modified: 2026-08-09T11:32:47.301Z
---

Verified 2026-08-09 during silent-lie sweep (chunk 1a of code+logic audit). Sampled last ~100k lines of `forecast_error_log.jsonl`, filtered to `field==pp` (n=7195):

- `applied_layer` = `"l1"` for 100% of rows
- `forecast_l1 == forecast_l2 == forecast` (top-level) for 100% of rows

**Why:** confirms `[[project_pp_recalibration_session]]` claim ("pp = L1-only in production"). The pp-branch decay tuning at `weather_collector/processors/decay_apply.py:82` (`L3_BRIER_FIELDS = {"pp"}`) does not currently produce distinct L2 values from L1 for pp. The top-level==L2 rule (`[[feedback_top_level_forecast_is_l2]]`) still holds; it just happens L2==L1 for pp.

**How to apply:** the three pp analysis scripts (`pp_brier_reliability.py`, `pp_brier_decomposition.py`, `h_pp_bias_persistence_stage0.py`) that read `r.get("forecast")` as the sole production source are correct — no `forecast_{applied_layer}` reconstruction needed. The 08-06 ppbp Stage 0 PROMOTE and the +43.5% pp BSS number rest on the correct baseline.

If pp ever gets a real L2 decay curve, or ppbp/other specialist starts writing distinct pp values, this equality breaks and the pp scripts DO need the reconstruction. Re-verify with the same applied_layer distribution check whenever pp's stack changes.
