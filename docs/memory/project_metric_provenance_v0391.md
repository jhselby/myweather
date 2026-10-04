---
name: project-metric-provenance-v0391
description: "2026-08-04 v0.6.391 metric provenance overhaul. Unified 7d cut (mae_over_time.json last_7d), auto-populated narrative, per-section audit label, PROD_PRIORITY registry with coverage test. Response to external review that flagged two same-labeled-different-value 7d numbers on the debug page."
metadata: 
  node_type: memory
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-04T14:55:01.130Z
---

# Metric provenance overhaul (v0.6.391)

## What shipped

1. **`analysis/mae_over_time.py` emits `last_7d` block** — n-weighted 7d rollup from per-day merged series, parallel shape to `last_24h`. Uses `sum(mae_d * n_d) / sum(n_d)` for MAE, sqrt(sum(brier*n)/sum(n)) for RMSE, weighted-bias same way. Single canonical 7d cut.
2. **Top per-field snapshot both 7d + 24h from same source** — `renderPerFieldSnapshot` in `corrections_debug.html` now overrides `pf-mae` cells from `mot.last_7d` inside the same fetch that populates `pf-today` from `mot.last_24h`. Falls back to `tsDoc.per_layer_mae_by_lead` unweighted mean of leads 1-47 if `last_7d` missing (fresh JSON, old schema).
3. **Auto-populated narrative** — hand-typed "Winning 7-day / Losing 7-day" block replaced with `<div id="pf-snapshot-narrative">` + JS that bins fields into Winning/Marginal/Losing from the same `last_7d` source.
4. **Per-section audit label** — `<div id="pf-snapshot-audit">` shows: 7-day window + method + source, 24-hour window + method + source, refresh timestamp, cell count sourced from last_7d vs fallback. Plus raw-difficulty index (see `[[project_raw_difficulty_index]]`).
5. **PROD_PRIORITY + _prodKey + _applied gap fix** — dpbp had just flipped LIVE but wasn't in any priority chain (silent-lie hazard: fallback would pick l4 for dp when prod_real missing). Added dpbp (dp) and wsbp (ws, kept for post-flip continuity). Both `_prodKey` implementations updated to match.
6. **`tests/test_prod_key_coverage.py`** — 4 tests: (a) PROD_PRIORITY covers every ENABLED specialist for its field, (b) _prodKey's priority array covers every specialist, (c) _applied maps every specialist to its field(s), (d) PROD_PRIORITY has `prod_real` as first entry for every field. Discovers ENABLED specialists from `weather_collector/processors/` via a `SPECIALIST_KEY_MAP` in the test file — new specialist adds one line. Full suite 19 → 23.

## Motivating problem

External reviewer flagged two different 7-day numbers on the debug page:
- Top per-field table: h −0.2%, ws +0.7% (from `tsDoc.per_layer_mae_by_lead`, unweighted mean of lead-1-47 MAEs)
- Narrative below: h +2.8%, ws +5.2% (hand-typed from a past sweep, stale)

Both correctly labeled "7-day," neither wrong for their definition, together indistinguishable to a reader making a ship decision. Same class as the metric-plumbing bugs this week (v0.6.390j applied_layer poison, v0.6.390o cl backfill, v0.6.390p wd L1_ONLY, v0.6.390y h_persistence_skill top-level forecast).

## Discipline codified

- `[[feedback_metric_provenance_labels]]` — every user-visible metric needs (source, window, method, refresh time). Two same-name-different-value metrics is the worst failure mode.
- `[[feedback_audit_label_direction_neutral]]` — name confounds, don't prescribe direction.

## What's NOT done (scope boundary)

- Hand-typed prose in per-field row descriptions, post-ship watches, calendar entries — still hand-typed. Joe explicitly OK with manual updates for prose fields; the specific problem this ship addresses is quantitative contradiction, not stale prose in general.
- Standardized-lift Phases 2-4 (difficulty-standardized correction lift, multi-dim difficulty score) — deferred. Only Phase 1 (raw-difficulty index alone) shipped. See `[[project_raw_difficulty_index]]`.

## Follow-ups

- When new specialists ship, add to `SPECIALIST_KEY_MAP` in `tests/test_prod_key_coverage.py`. The test will fail loudly if the debug page's priority chains don't cover them.
- Audit remaining processors for embedded-constant dicts that a fitter regenerates daily (Lsr was the last known cloud/solar case; others may exist).
- `[[project_top_level_forecast_sweep]]` still open — 3 strong + 3 weak analysis-script suspects reading top-level forecast as Production.

## Related

- `[[feedback_debug_page_canon]]`
- `[[feedback_debug_page_full_sweep]]`
- `[[feedback_metric_provenance_labels]]`
- `[[feedback_top_level_forecast_is_l2]]`
- `[[feedback_shadow_write_applied_layer_trap]]`
- `[[project_raw_difficulty_index]]`
- `[[project_08_04_session]]`
