---
name: project-dpbp-live
description: dp_bias_persistence flipped ENABLED=True 2026-08-04 v0.6.391. First antecedent-error specialist LIVE. 14-day post-flip watch CLOSED CLEAN 2026-08-18. Preflight step-2 pair-log stamp gap flagged as follow-up.
metadata: 
  node_type: memory
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-18T13:09:42.424Z
---

# dpbp status: LIVE — watch CLOSED CLEAN 2026-08-18

**Watch close (08-18 v0.6.430b):** 14-day post-flip window elapsed. Regression sentry (sustained 7d vs fresh 3d) clean on dp; layer-shape sentry clean on all applied bands. Today's anomaly-detector dp WATCH +32% MAE is a shared distribution shift (bin_shift +29.7pp; h similarly WATCH +6.5%) — a weather event, not attributable to dpbp's narrow gated firing pattern. dpbp stays LIVE with no follow-up damage; the shadow-key pair-log stamp gap (below) remains a follow-up for future flips of this class.

**Flip:** 2026-08-04 v0.6.391 after 7-day shadow-week gate cleared. Shipped ENABLED=False 07-28 v0.6.387.

**Gate:** `regime ∈ {pre_frontal, nw_flow, sw_flow} AND lead ≥ 6h AND prev_24h_dp_bias(regime) < -1.5°F` → add +2.0°F to hourly dew point.

**Stage 1 verdict (07-28):** pooled dp MAE 3.108 → 2.808 (+9.63% pooled). Per-regime halves-verified: pre_frontal +17.23% (halves +21.6/+12.0), nw_flow +14.51% (+15.6/+13.8), sw_flow +14.62% (+6.1/+17.9).

## Preflight verified at flip

- Code unchanged since 07-28 ship (single commit d095cb7).
- Params match Stage 2 output (trigger −1.5, correction +2.0, min_lead 6, 3 focus regimes).
- Shadow write firing +2.0°F per lead in nw_flow (38 leads at flip tick).
- dp Last-24h at −3.2% vs raw (healthy baseline pre-flip).

## Preflight gap (follow-up)

`corrected_dew_point_shadow_dpbp` exists per tick in `weather_data.json` but is not stamped in the pair log. So the preflight step-2 walkforward recheck (shadow-vs-live comparison over the 7d gate) could not be run. Same infrastructure gap likely existed at chp/wdp flip time.

Follow-up: give dpbp the wdp/clp v0.6.382p treatment — stamp shadow key to `forecast_error_log.jsonl` so future ENABLED=False → True flips have a measurable pre-flip gate. Add to `[[project_top_level_forecast_sweep]]` sibling list.

## Post-flip watch (through 08-18)

- 14 days.
- Track dp per-lead MAE by regime (should improve on nw_flow-heavy periods where the antecedent bias hits the trigger).
- Any of the 3 focus regimes regressing worse than v0.6.387-baseline once n ≥ 200 rows/regime.
- Overall dp MAE drifting up.

## Post-flip verify (immediate)

- `dp_bias_persistence.enabled: true` ✓
- Correction magnitude on fired leads: `hourly.corrected_dew_point[i] - hourly.corrected_dew_point_pre_dpbp[i]` = +2.0°F where fired ✓
- Non-firing regimes (sw_flow at above-trigger bias): 0 leads fired ✓

## Sibling status

- **wsbp** (`ws_bias_persistence`): flip HELD 08-04 — calm regime n=0 in 7-day shadow-log window. See `[[preflight_wsbp]]`.

## Related

- `[[project_07_28_post_reboot]]` — the ship arc.
- `[[project_hypothesis_backlog]]` — backlog #6 closed by this flip.
- `[[preflight_dpbp]]` — the checklist that was followed.
- `[[project_top_level_forecast_sweep]]` — sibling infra gap list.
