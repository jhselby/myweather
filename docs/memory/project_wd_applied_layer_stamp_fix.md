---
name: wd-applied-layer-stamp-fix
description: "v0.6.400 (2026-08-09) — collector fix for wd pair-log rows missing applied_layer. Bug silent since v0.6.269. Consequence: wdp firing cells invisible to production MAE + gate metrics."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8936b8c9-2577-4ecc-9d6b-6658da634b60
  modified: 2026-08-09T13:44:56.626Z
---

**Ship:** v0.6.400 on 2026-08-09. `weather_collector/processors/forecast_error_log.py`.

**Bug:** the wd branch at line 184 takes an early `continue` at line 219-220. That skipped the `applied_layer` stamp block at the bottom of the loop body. Every wd pair-log row has been missing `applied_layer` since applied-layer stamping shipped in v0.6.269.

**Blast (revised 08-09 after user correction):** verified 08-09 on 21,494 wd rows in `~/.cache/myweather/forecast_error_log.jsonl` — 0/21494 had `applied_layer`. 762 rows (~3.5%) had `forecast_wdp != forecast_l4`. BUT `mae_over_time.py:53` explicitly has `wd` in `L1_ONLY_FIELDS` with an explicit workaround (lines 174-177 comment: "Applied-layer stamping isn't used for L1_ONLY_FIELDS (wd has no applied_layer key), so prod_real is computed differently for wd") — walks `error_l2` then deepest specialist directly. So the debug page, WINNING FIELDS tile, and Accuracy chart for wd were ALREADY correct since 08-02 (`[[feedback_l1_only_field_routing_trap]]` fix). Real impact of v0.6.400 fix is narrower than initially claimed:

- `decay_fit.py` Fitter — its fallback walked l1-l6 and landed on l1/l2 for wd, missing wdp. Now picks wdp correctly on ~3.5-8% of rows. Feeds `decay_corrections.json`.
- Any analysis script keyed strictly on `applied_layer` stamp (small set).
- NOT the debug page (uses mae_over_time.py's L1_ONLY branch which never needed the stamp).
- NOT the 07-27 wdp flip metric (that's `h_wd_persistence_gate_stage*.py` and doesn't route through applied_layer — its bug is the separate top-level=L2 issue tracked in `[[project_top_level_forecast_sweep_1b]]`).

Initial claim "wd Production == L1 for months" was WRONG. The wd Prod line has been honest since 08-02 via mae_over_time's workaround.

**Why (concrete history):** discovered during silent-lie sweep (chunk 1 of 08-09 code+logic audit) after `[[project_top_level_forecast_sweep]]` rescope revealed `applied_layer` missing entirely for wd. Related bug class: `[[feedback_shadow_write_applied_layer_trap]]`, `[[feedback_top_level_forecast_is_l2]]`.

**Fix:** stamp applied_layer inside the wd branch before `pairs.append(pair)`, matching the pattern the non-wd branch had at lines 253-258.

**How to apply:**
- Fresh clean-data window starts on next Cloud Function tick after 08-09 deploy. Historic rows stay missing the field.
- Re-verify wdp's real production contribution once ~7d of clean data accrues.
- The 07-27 wd flip decision was made on a broken metric — don't assume it's still correct. Re-cut the wd gate stage script after fixing the analysis-side top-level-forecast trap (chunk 1b of the same audit).
