---
name: project-raw-mae-reversal-tripwire
description: 🚨 Open workstream. The stack has no mechanism to catch a source-model raw-MAE collapse in real time — all five routing overrides key off prod-MAE which lags 7d. The 09-19 to 09-26 ws bleed exposed the gap. Design a raw-MAE reversal tripwire before the next event.
metadata: 
  node_type: memory
  type: project
  modified: 2026-09-26T11:40:41.654Z
  originSessionId: b263e9cd-d969-4acf-add7-b0c4f9f5625c
---

# Raw-MAE reversal tripwire — open workstream

## What broke

Between 2026-09-19 and 2026-09-26, ws Prod went from +2.32 MAE (well below raw 3.04) to +6.18 MAE (60% worse than raw 3.86). Root cause: L1 selector routes ws to NBM on all 4 bands (30d evidence: NBM +2.4 to +13.5% lift, recent 7d up to +26%). NBM raw for ws cratered starting 09-23 (raw_nbm 3.80 → 6.51 while raw_hrrr held 3.46-3.86). Prod tracked NBM. **No mechanism caught it.**

Full 09-26 ws layer numbers (from `mae_over_time.json`):

```
              09-23  09-24  09-25  09-26
raw (hrrr)    4.98   4.30   3.46   3.86    ← what we'd have gotten
raw_nbm       3.80   3.74   5.35   6.51    ← what we chose
prod_real     3.59   3.54   5.03   6.18    ← what shipped
```

By-field trajectory for the same window shows wg also bleeding, but wg is a metric artifact (raw_wg cratered from 5.80 → 12.08 due to windy weather; the wg correction is still winning on the walker). **ws is the real regression.**

## Why the existing five mechanisms miss it

`pick_source()` precedence: HRRR PBL workaround → `_LEARNED_CELLS` → `_IMS_SELECTOR_CELLS` → by-regime walker → band pool → HRRR fall-through. All five downstream mechanisms score picks by prod-MAE on 7d+ pools:

1. **Band pool table** — 30d pool-based, recency override on 7d prod-MAE. 7d rolling window means a 2-3 day raw-MAE collapse takes ~5-7d to shift the recency signal.
2. **By-regime walker** — 7d walker with per-day thin gate. Same lag.
3. **IMS threshold** — signal is `ims = |L1 - raw_nbm|`, not a comparison of raw quality between sources. Blind to source-side reversal.
4. **GBM classifier (v0.7.5)** — features include ims, xr_spread, cc_inter_sigma. Same problem: encodes disagreement, not source quality reversal.
5. **HRRR PBL workaround** — hardcoded, t-only.

**No mechanism looks at raw MAE. All five key off prod-MAE (7d+).** By the time prod-MAE reflects a raw collapse, we've bled through the whole delay.

## The tripwire

Add a sixth precedence layer, between HRRR-PBL and `_LEARNED_CELLS`:

> If, for this (field, band), `mean(raw_nbm_MAE)` over the last N days > `mean(raw_hrrr_MAE)` × K, AND the current pick is NBM, override to HRRR.

Symmetric: if raw_hrrr > raw_nbm × K and pick is HRRR, override to NBM.

**Parameters (design questions):**
- N (consecutive days): 2 would have caught 09-25 → 09-26. 3 is safer against noise.
- K (reversal magnitude): 1.3 based on the ws data (NBM 5.35 vs HRRR 3.46 = 1.55×). Could be tighter.
- Scope: per (field, band) or per field? Bands ripple differently for the same source model shift.
- Minimum n: rows per day to trust the daily raw MAE.
- Recovery: how many consecutive days back to normal before releasing the override.

## Data plumbing

Data source is already there: `mae_over_time.json`, series[field].raw and .raw_nbm, per obs-day. Publisher writes it hourly. Runtime read cost is negligible.

Runtime lookup: in `pick_source()`, before any per-obs check, consult a small cached `_RAW_REVERSAL_OVERRIDES` dict {(field, band): "hrrr" | "nbm"} that a nightly analysis populates. Same shape as `_IMS_SELECTOR_CELLS` — no runtime MAE computation, just a table lookup.

## Ship path

1. **Diagnostic first**: `analysis/raw_mae_reversal_sentry.py` — over the last 90d of `mae_over_time.json`, for each (field, band, day), compute the reversal signal. How often would it have fired? On which fields? What N/K trip on real reversals vs. noise?
2. **Design gate**: if signal-to-noise is workable, commit the sentry as scheduled analysis.
3. **Shadow**: wire the override table + reader in `l1_selector.py`, load from a new curated JSON, ship with an ENABLED flag off.
4. **7d shadow accumulate + validate**: check the shadow decisions on `pair_log` — would they have improved served Prod?
5. **Flip**: one-line flag flip, same rollback discipline as v0.7.5.

## Non-goals

- Not a general-purpose "correct routing when models disagree." That's the entire selector problem; the point of this layer is specifically **source-collapse detection**, which the other five mechanisms structurally can't do.
- Not a manual override list. The value is that it's automatic and catches future events, not just the 09-26 ws case.
- Don't ship reactive per-field emergency overrides for the current ws bleed. The user's call 09-26: "accept the bleed, don't whipsaw." Discipline preserved.

## Related

- [[project_09_26_session]] — session where this was identified.
- [[project_router_as_authority_pivot]] — v0.7.5, the fifth mechanism, ships ~1h before this workstream was scoped.
- [[project_selector_recency_override_watch]] — the existing recency-override checkpoint documents the "don't tighten on short windows" discipline this tripwire has to respect.
- [[feedback_stack_health_trajectory_over_tile]] — 09-26 lesson on when to trust the trajectory chart. This project is why the trajectory tail was actually right and the tile deserved the diagnosis I initially dismissed.
