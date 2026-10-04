---
name: pr-l2-gate-ordering-fix
description: "v0.6.402 (2026-08-13) — collector ordering fix. pr L2 regime gate shipped 08-10 v0.6.401 had NEVER fired live because stamp_state ran AFTER add_corrected_hourly_arrays. Backstamp early read: gated-vs-raw −5.19% on 2,688 rows post-08-10. 14-day post-fix watch begins 08-13."
metadata: 
  node_type: memory
  type: project
  originSessionId: 75594b57-90bb-4c30-ac91-26cf9ced6bf0
  modified: 2026-08-13T11:14:13.490Z
---

# pr L2 gate ordering fix (v0.6.402, 2026-08-13)

**Bug:** `weather_collector/collector.py` ran `add_corrected_hourly_arrays` (line 238, contains the pr L2 regime gate) BEFORE `stamp_state` (line 353, writer of `derived.state.regime_synoptic`). Every tick the gate read `regime = None`, guard `if regime is not None` short-circuited, and **zero pr L2 cells fired between 2026-08-10 ship and 2026-08-13 fix**.

**Detection:** pair-log audit — 2,688 pr rows post-08-10 with 0 stamped `applied_layer=l2` (813× l1, 1,875× l3, all `l3` cases have `_post_l3 == raw` which only happens when live-apply skipped and `corrected_pressure_in = list(raw_pressure_in)`). Debug page Production line = 0.0% vs raw, prompting Joe to notice.

**Fix:** moved `stamp_state` try/except block to immediately before `add_corrected_hourly_arrays`. `state_stamp` deps (`current`, `derived.pressure_trend_hpa_3h`, `hourly.wind_direction/speed/pressure/temp/time`) are all populated by line 226, so the move is safe. See `weather_collector/processors/state_stamp.py` — reads current + hourly base arrays, no dep on corrected_hourly output.

**Backstamp early read** (`scratchpad/pr_l2_backstamp.py` — simulates live-apply using `state_obs.regime_synoptic@lead=0` of the same run_time, which is what the live gate reads at run-time):

| bucket | n | MAE | vs raw |
|---|---|---|---|
| raw (L1) | 2,688 | 0.02111 | — |
| simulated gated apply | 2,688 | 0.02002 | **−5.19%** |
| L2 shadow everywhere | 2,688 | 0.01876 | −11.13% |

Fire-cell detail — both cells match Stage 1 predictions:
- **nw_flow 0-5h: n=223, Δ −43.64%** (Stage 1: A +21.8% / B +41.6%)
- **nw_flow 6-11h: n=221, Δ −21.93%** (Stage 1: A +10.3% / B +13.1%)

**Secondary issue (not fixed):** `forecast_snapshot.py:246-249` unconditionally overwrites top-level `pr` with `pr_l2` in every pair-log row, even skip cells. That's why every post-08-10 pair-log row has `forecast == forecast_l2` regardless of what live-apply did. Documented rationale is Fitter calibration continuity (top-level must equal L2 pre-decay so Fitter sees real error, not 0). Same class as [[feedback_top_level_forecast_is_l2]]. Metric-side confusion is real but the shadow behavior is by design. If pr L2 metric ever looks wrong post-fix, revisit.

**Live-verification pending (2026-08-13):** deploy went out at 10:23 UTC (`make deploy-collector` → revision `myweather-collector-00489-hil`). Last successful GCS tick was 09:17 UTC — every tick since has failed at `fetch_parallel_sources` with `TimeoutError: 1 (of 12) futures unfinished`, traced to GoMOFS opendap.co-ops.nos.noaa.gov 30s read timeouts cascading through the parallel fetcher. **Unrelated to this fix** — it's an upstream data-source outage. First successful tick will confirm the gate fires (`hourly.corrected_pressure_in != hourly.raw_pressure_in` on short-lead nw_flow indices when current regime = nw_flow). Verifier: `curl -s https://storage.googleapis.com/myweather-data/weather_data.json | python3 -c "..."` — see conversation-end verifier snippet.

**How to apply:**
- 14-day post-fix watch begins **2026-08-13**, closes ~**2026-08-27**.
- Re-run `scratchpad/pr_l2_backstamp.py` against real `applied_layer=l2` rows once 7d of clean data accrue — confirm reality matches simulation.
- If overall gated-vs-raw stays around −5% and both fire cells stay winning, pooled-only Stage 1 WINs (nw_flow/12-23h, pre_frontal/{0-5,6-11}, sw_flow/{0-5,6-11}) become fair candidates for expansion per `[[feedback_whitelist_promotion_gate]]`.
- **Adjacent audit-chunk 1b:** check every regime-gated live-apply gate (chp, clp, wdp, wd_l2 blend, Ccd, sr Lsr, Lsb) for the same `stamp_state`-order dependency. Each specialist that reads `derived.state.regime_synoptic` at its own line-number position is safe now (state_stamp moved up); the audit is verifying none of them run BEFORE add_corrected_hourly. Fresh audit welcomed.

**Related:**
- [[feedback_top_level_forecast_is_l2]] — top-level forecast leakage class
- [[wd-applied-layer-stamp-fix]] — v0.6.400 analogue (different mechanism, same class of "gate looks fired but metric reports raw")
- [[project_pr_l2_regime_gate_opportunity]] — original Stage 1 investigation
- [[project_pr_l2_regime_flip_investigation_08_10]] — Stage 2 → Stage 3 flip decision
