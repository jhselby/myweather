---
name: project-09-27-session
description: "🚨 v0.7.7 shipped to collector (mechanism attribution stamp + retro scorer for v0.7.6) but NOT committed to git — resume by committing weather_collector/processors/{l1_selector,forecast_snapshot,forecast_error_log}.py + index.html + docs/CHANGELOG.md + new analysis/l1_static_blend_shadow_verify.py. Also: 24h scorecard shows sr/wg/t losing to raw_nbm — watch 09-28/29, if holds it's a v0.7.4/v0.7.5 audit trigger. Off-curated stamping bug documented for pre-flip fix."
metadata: 
  node_type: memory
  type: project
  originSessionId: ad64ef3c-83c1-4ff6-8a50-0b6a8cf3ba6c
  modified: 2026-09-28T11:13:46.207Z
---

# 2026-09-27 Sunday session — v0.7.7 telemetry ship + digest triage

## ⚠ Resume state: v0.7.7 deployed to collector, NOT yet committed

Joe deployed `make deploy-collector` this morning after my edits; GCS pair-log has been carrying `selector_mechanism` and `l1_blend_shadow` on fresh ticks since. But the working tree is uncommitted:

- `weather_collector/processors/l1_selector.py` — new `pick_source_with_mechanism()`
- `weather_collector/processors/forecast_snapshot.py` — stamps `{f}_selector_mechanism`
- `weather_collector/processors/forecast_error_log.py` — pair-log passthrough
- `index.html` — v0.7.6 → v0.7.7
- `docs/CHANGELOG.md` — v0.7.7 entry at top
- `analysis/l1_static_blend_shadow_verify.py` — new file, UNTRACKED

Everything else in `git status` is daily walker/curated JSON churn — leave alone.

## What shipped (v0.7.7)

**Mechanism attribution.** `{f}_selector_mechanism` now stamped alongside `{f}_selector_source`. Values: `pbl_morning_kill` / `learned_gbm` / `ims_threshold` / `regime_override` / `band_pool` / `default_hrrr`. Confirmed live via GCS scan — 8 stamped rows in last 300KB, `ch` correctly attributed as `ims_threshold`. Unblocks the 10-03 v0.7.5 verdict: per-cell Value-Captured on ch/sr can now be attributed cleanly to the router vs. precedence-chain coincidence. See [[project_router_as_authority_pivot]].

**v0.7.6 retro scorer.** New `analysis/l1_static_blend_shadow_verify.py`. Reads `l1_blend_shadow` stamp on covered (regime, band) cells from local raw pair-log (backstamped GCS is stale by 3d — see [[project_backstamp_stale_09_24]]). Computes 7d + 30d served/blend/L1/raw_NBM MAE per cell, halves-stable A/B split. Verdict values: SHIP-READY / HOLD / KILL / THIN. Publishes to `gs://myweather-data/l1_static_blend_shadow_verify.json`. Digest driver auto-picks it up. This is the flip gate for v0.7.6 apply on ~10-03.

## Real finding — off-curated stamping bug (pre-flip TODO for v0.7.6)

12h post-v0.7.6 window: 93 shadow-stamped rows, only **15 in curated cells** (14 pre_frontal + 1 nw_flow). **78 rows landed in `nor_easter` cells that are NOT in the curated JSON.** Root cause: `forecast_snapshot.py` line 1100 passes its own per-lead `_fc_regime_i` to `l1_static_blend.blend_l1()` for the stamp decision, but `state_stamp.py` later writes a *different* `regime_synoptic` value into `entry['state_fc']`. The pair-log records the state-stamp regime; the stamp used the forecast-snapshot regime.

Consequence: an `ENABLED=True` flip would silently apply the blend to cells the halves-stable gate never approved. **Must reconcile the two regime labels before the v0.7.7-equivalent apply flip on v0.7.6.** Documented in the CHANGELOG entry. Both source paths need a shared regime resolver — TBD which one is "correct."

Not a runtime issue while `ENABLED=False`.

## Digest triage read

**Nothing to ship today.** walkforward's proposed config matched live. LSR gated 1/7. `h_h_residual_persistence` flipped info→STAGE 1 PROMOTE (+2.66% MAE, 2/3 regime WIN, halves both positive) — queue Stage 2 preview this week. `h_h_dp_tau_refit` labeled kill→promote but body says HOLD — label mismatch, treat as HOLD.

**Alarms worth naming:**
- 🔥 `ws FRESH FIRE` (sentry 7d -5.3% / 3d +23.8%) — real, not lucky-baseline: 09-25 prod_real (5.03) beat raw (3.46) by -45% same day v0.7.4 skip-removal shipped. 09-26 also weak. 09-27 recovered clean. Watch, don't intervene — the 09-25 dip will roll off in 2 days.
- ★ `sr.l3_nbm HOT` (help +6.5% → -2.4% Δ+8.8pp) — sr just moved to GBM routing Friday. Possible interaction. Read at 10-03.
- ★ `MLC in-bin bias COLLAPSE` (-3.24 → +13.30) — MLC is `ENABLED=False` sandbox, no live impact.

## 24h regime shift — mid-session finding

Late in the session, checked the 24h scorecard slice (window: 09-26T11:16 → 09-27T11:16):

| field | 24h lift | 7d lift | delta |
|---|---|---|---|
| ch | +55% | +57% | flat |
| h | **+43%** | +1% | up huge |
| ws | +2% | +3% | flat |
| t | **-17%** | +2% | collapsed |
| wg | **-39%** | +7% | collapsed |
| sr | **-68%** | -4% | collapsed hard |

7d picture was 5-1-0 (winning/flat/losing). 24h collapsed to 3-0-3 on the same 6 fields. **This is the regime-shift test I named** in the 7d review. Three fields with recent ship activity (sr router, wg v0.7.4 unskip, t no ship) all losing today.

**If sr and wg stay negative on the 24h through 09-29, that's a v0.7.4 / v0.7.5 audit trigger — not a "wait for it to roll off" case.** Check tomorrow's tick first thing.

## ws 09-25 regression evidence (for the v0.7.4 audit if triggered)

Daily ws MAE around v0.7.4 ship (09-25):

| date | raw | prod_real | prod vs raw |
|---|---|---|---|
| 09-24 | 4.30 | 3.54 | +18% ✓ |
| 09-25 | 3.46 | **5.03** | **-45%** ❌ |
| 09-26 | 3.16 | 3.77 | -19% ❌ |
| 09-27 | 4.21 | 3.16 | +25% ✓ |

v0.7.4 unskipped l3_nbm/wg/sea_breeze/6-11h. Two-day dip on ws (wind-adjacent) suggests possible interaction; single-day recovery makes it not-conclusive alone. Combined with 24h wg -39%, worth an audit if it persists.

## Related
- [[project_router_as_authority_pivot]] — mechanism attribution now live
- [[project_l1_static_blend_v076]] — retro scorer available + off-curated bug found
- [[project_09_26_session]] — Friday's dual ship (v0.7.5 + v0.7.6)
- [[project_backstamp_stale_09_24]] — GCS backstamped log still ~3d stale; local raw pair-log used for the retro scorer instead
- [[feedback_fresh_fire_lucky_baseline_artifact]] — ws fresh fire is NOT artifact; genuine regression on 09-25
