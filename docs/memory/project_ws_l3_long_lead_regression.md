---
name: ws-l3-long-lead-regression
description: "Wind speed L3 is enabled in production but the per_layer_mae_by_lead chart shows it making ws forecasts 20–31% worse at leads 18–47h. The walkforward validator's per-field aggregate hides this. Queued: add per-band columns to the walkforward output, then drop ws from L3 (or wire a per-band whitelist) once the per-band view confirms. **07-28 UPDATE: this whole narrative was partly hiding a bigger L2 blend problem.** ws L3 asymmetric SKIP additive (v0.6.370) is now bit-identical to L2 at every lead per TSD; the ws +30% Prod-vs-Raw regression was actually driven by wind_blend.py's 24h observation-bleed (fixed 07-28 v0.6.384 by shrinking BLEND_HOURS to 4). L3 SKIP additive is doing its job — the 26 SKIP cells legitimately catch L3 damage at edge cases — but was never the main lever. See v0.6.384 in [[project_07_28_session]] and updated ws row in [[project_todo]]."
metadata: 
  node_type: memory
  type: project
  originSessionId: a8f5db73-5a54-4321-a927-279049b8212d
  modified: 2026-07-28T13:07:09.058Z
---

## What we observed (2026-06-26 Fitter snapshot)

Per-(field, lead) MAE from `time_series_diagnostic.json`, current production stack:

| lead | ws L2 | ws L3 | ws Δ | wg L2 | wg L3 | wg Δ |
|---|---|---|---|---|---|---|
| 0–2h | 2.01 | 2.04 | +1.2% | 2.80 | 2.83 | +0.9% |
| 6–12h | 3.27 | 3.34 | +2.4% | 4.96 | 4.93 | −0.5% |
| 18–22h | 2.85 | 3.45 | **+18 to +29%** | 5.42 | 5.00 | −7.8% |
| 24–46h | 2.77–3.06 | 3.54–3.75 | **+20 to +31%** | 6.38–7.65 | 5.29–6.52 | −15 to −22% |

Sustained wind (ws) L3 hurts at every lead and goes from "small mistake" to "large regression" by 18h+. Gusts (wg) L3 is approximately flat at short lead and **helpful** by 12 to 22% at long lead — the opposite shape. Same layer, different field, opposite verdict by lead band.

## Why ws and wg disagree

L3 = per-`(field, lead_h)` median forecast-vs-obs bias, applied as an additive nudge.

- **wg** is dominated by synoptic flow strength; its model bias at long leads is structurally consistent (the model systematically over-predicts gusts when the trend has settled), so the median bias is a real signal. L3 catches it.
- **ws** is locally driven (terrain channeling, sea-breeze, friction). The "median bias" at lead 40 is a fiction — half the time the model is over, half under. The L3 nudge pushes forecasts in the wrong direction half the time, doubling errors instead of canceling them.

The walkforward L3/L4 validator reports **one aggregate MAE per field across all leads**, so the short-lead near-neutrality + long-lead damage average to "still net win" on some windows. That's why ws is currently in `L3_FIELDS`.

## Queued plan (do not act today)

**Why:** real architectural change to the layer-on/off decision system; needs deliberate review, not a same-day fix. Joe's call (2026-06-26) was to queue rather than edit production now.

**How to apply:**

1. **First — make the diagnostic honest.** Add per-band columns to `analysis/walkforward_l3l4_validator.py`'s output (the per-field MAE table). Already-present BANDS list `[0-5h, 6-11h, 12-23h, 24-47h]` exposes the lead structure; surface the same columns at the field level so the recommendation row carries band-level verdicts. Target: 06-29 walkforward read shows `ws: 0-5h OK, 6-11h OK, 12-23h FAIL, 24-47h FAIL` instead of `ws: on`. Half an hour of work.
2. **Then — drop or band-gate ws L3.** Two options once the per-band view is live:
   - Conservative: remove `ws` from `L3_FIELDS` in `decay_apply.py`. Loses the genuine short-lead help but kills the long-lead regression.
   - Right shape: add a per-(field, lead_band) whitelist alongside `L3_FIELDS` so `ws` can be on for 0–11h and off for 12–47h. New surface in `decay_apply.py`; small refactor.

**Why option 2 is the right shape:** other fields will eventually want per-band gating too (cc/cm/cl already show lead-dependent behavior in the walkforward output today). Building the per-band whitelist once unlocks all of them.

## Where the data lives

- Per-lead MAE source: `data.wymancove.com/time_series_diagnostic.json` (Fitter writes every cycle).
- Walkforward validator: `analysis/walkforward_l3l4_validator.py` (per-field aggregate today; needs per-band rollup).
- Production whitelist: `weather_collector/processors/decay_apply.py` `L3_FIELDS`.
- Walk-forward gate-history thread: [[project-walkforward-l3l4-validator]].

Related: [[project-walkforward-l3l4-validator]], [[feedback-whitelist-promotion-gate]].
