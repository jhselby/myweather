---
name: simpson-guard-shadow
description: "09-13 shadow — Simpson-paradox guard on L1 recency override. Shadow measurement PROVES the guard would REGRESS prod by pooled -14.2% on the flagged cells; recency mechanism vindicated even on Simpson-shaped flips. h 24h regression diagnosed as short-lived HRRR-favorable pattern, not a routing bug."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8ada5941-fc99-42cb-96e7-a45abbd78adf
  modified: 2026-09-13T22:39:53.501Z
---

# Simpson-guard shadow — recency override vindicated

Shipped as SHADOW-ONLY 2026-09-13 evening (runtime unaffected). Investigating whether the L1 recency override could produce Simpson's-paradox flips: pooled 7d disagrees with 30d, but every per-regime 30d agrees with 30d pool pick.

## What was shipped (shadow-only, no runtime change)

`analysis/l1_selector_fit.py` — added per-regime 30d accumulator + Simpson-guard shadow. New per-cell fields: `simpson_guard_would_veto` (bool), `source_under_simpson_guard` (str), `simpson_guard_note` (str). New top-level `simpson_guard_shadow` block with vetoed-cell list + parameters.

`analysis/simpson_guard_shadow.py` — new script. Reads curated table for vetoed cells, re-scans pair-log over 7d, computes pooled prod-MAE under `source` (current) vs `source_under_simpson_guard` (counterfactual). Writes `analysis/output/simpson_guard_shadow.json`, publishes to GCS `simpson_guard_shadow.json`.

Guard parameters: `SIMPSON_GUARD_MIN_N_PER_REGIME=100`, `SIMPSON_GUARD_MIN_MEASURED_REGIMES=6`, `SIMPSON_GUARD_MIN_AGREE=7`, `SIMPSON_GUARD_MIN_MEDIAN_LIFT_PCT=20.0`.

## The finding — 09-13 evening

Of 9 recency overrides, shadow flagged 5 as Simpson-shaped (sr all 4 bands + dp/0-5). Preserved: t/24-47, wg/0-5, wd/0-5 (30d marginal, regime split); dropped from flag list this fit: h/0-5 (recency override didn't fire — 7d lift +0.3%, under threshold).

**Shadow 7d prod-MAE measurement (counterfactual: what if guard were on):**

| cell | cur→ | grd→ | cur MAE | grd MAE | Δ% | n |
|---|---|---|---|---|---|---|
| sr/0-5 | nbm | hrrr | 41.45 | 44.00 | **-6.2%** | 895 |
| sr/6-11 | nbm | hrrr | 43.80 | 50.89 | **-16.2%** | 900 |
| sr/12-23 | nbm | hrrr | 45.82 | 50.64 | **-10.5%** | 1800 |
| sr/24-47 | nbm | hrrr | 49.18 | 53.41 | **-8.6%** | 2016 |
| dp/0-5 | nbm | hrrr | 1.31 | 1.43 | **-8.9%** | 890 |
| POOLED | | | 39.98 | 45.66 | **-14.2%** | |

**Verdict:** every cell would regress under the guard. Guard NOT shipped. Recency mechanism is genuinely picking up real 7d shifts that 30d per-regime data (30 days of stale-mixed weather) misses.

**Why:** The 30d per-regime table shows HRRR winning ~40-70% raw at sr and dp — but that's stale. The last 7d had a real regime shift where NBM cascade actually delivers lower prod-MAE on these cells despite historical per-regime data pointing at HRRR. The pooled 7d lift caught it; the guard would have vetoed it based on stale per-regime evidence.

## Ongoing measurement

Shadow infra stays. `simpson_guard_shadow.py` runs on-demand (not yet scheduled). If pooled `delta_mae_pct` ever flips positive for a sustained window, revisit — until then the guard as designed is confirmed harmful.

## Also: h 24h regression is not a routing bug

Diagnosed in the same session. Post-fit h 24h: HRRR raw=5.03, NBM raw=9.28, l1sel=7.09, prod=8.69, sel_h=-41%. Layer-by-layer:

| band | HRRR L2 | L2_NBM (applied) | n | applied_layer |
|---|---|---|---|---|
| 0-5 | ~3.65 | 6.02 | 45 | 100% l2_nbm |
| 6-11 | ~3.60 | 9.02 | 48 | 100% l2_nbm |
| 12-23 | ~5.80 | 10.11 | 96 | 100% l2_nbm |
| 24-47 | ~5.56 | 8.03 | 184 | 92% l2_nbm |

HRRR-side cascade would beat L2_NBM in every 24h band. But 30d by-regime prod-vs-prod shows NBM wins at h/6-11 (7/8 regimes, +5.7% to +25.6%) and h/12-23 (7/8 regimes, +2.8% to +31.6%). Selector correctly holds NBM. This is a short-lived HRRR-favorable pattern; if it persists, 7d recency will flip h/6-11 (currently +18.6% NBM) toward HRRR in 3-4 more days automatically.

**One flagged watch item:** L2_NBM MAE on h/6-11 (9.02) is barely different from NBM raw (9.06) — the NBM-side station-bias Kalman is doing nothing on that cell in the 24h window. Compare h/0-5 where L2_NBM=6.02 gives -35% over raw. Likely stale/thin Kalman state on h/6-11. Not urgent, log-only.

## Related

- [[project_selector_recency_override_watch]] — Checkpoint 2 verdict "DO NOT tighten threshold" reinforced by this shadow finding.
- [[project_09_13_session]] — session it was built in (evening add).
- [[feedback_shadow_write_applied_layer_trap]] — the trap we avoided by choosing shadow-annotation over runtime shadow-write.
- [[project_wyman_cove_hrrr_l1_biases]] — HRRR humidity bias context that made the h 24h dig interesting.
