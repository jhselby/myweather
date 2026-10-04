---
name: h-residual-persistence-attribution-08-30
description: "2026-08-30 attribution finding + un-skip. dp Stage 1 PROMOTE (+21.25% aggregate, 5/5 WIN) matched by fresh h Stage 1 (+21.41%, 5/5 WIN on same 5 regimes) — signature of a single upstream h bias observed twice via Magnus. t Stage 1 exonerated (+1.46%, 3/5 LOSE). h Stage 1 un-skipped v0.6.520; verdict MARGINAL blocked only by halves stability; earliest re-check 09-02."
metadata: 
  node_type: memory
  type: project
  originSessionId: a2ab4a67-4b42-44ae-96d9-f5c9f5f02ecb
  modified: 2026-08-30T21:09:06.590Z
---

# h residual-persistence — architectural attribution 2026-08-30

## The finding

Today's digest promoted `h_dp_residual_persistence_stage1` MARGINAL → PROMOTE: aggregate +21.25% MAE lift, per-regime 5/5 WIN, halves both positive. Per [[project_dp_is_derived_no_dp_work]] `dp = Magnus(t, h)` so a dp-side signal is architecturally a downstream echo of a t or h bias.

Ran companion Stage 1 for h and t using the **exact same methodology** (dp Stage 1 script cloned in scratchpad, only FIELD swapped, same window grid, same 7-day test window, same per-regime cross-cut, same halves check):

| Field | ΔMAE aggregate | Per-regime | Halves | Verdict |
|---|---:|---|---|---|
| dp (digest) | +21.25% | 5/5 WIN | both positive | PROMOTE |
| **h** (fresh v0.6.520) | **+21.41%** | **5/5 WIN** (same 5 regimes: nw_flow, pre_frontal, se_flow, sea_breeze, sw_flow) | sign flip (first −0.93%, second +3.12%) | MARGINAL |
| t (scratchpad) | +1.46% | 2 WIN / 3 LOSE | sign flip | HOLD |

h and dp lift are **statistically indistinguishable** (+21.41% vs +21.25%, both 5/5 regime WIN on the same 5 regimes). That's the diagnostic signature of a single h bias observed once directly and once one derivation-step downstream in dp.

Companion per-cell lag-1 autocorr check at the 3 dp SHIP cells (sw_flow/12-23, sw_flow/24-47, se_flow/24-47) confirmed h has real per-hour signal at 2 of 3 cells; t is broadly clean. Only exception is se_flow/24-47 evening cluster (h00, h19-h21) where t carries signal but h does not — the one cell that might warrant a dp- or t-side follow-up.

## What shipped v0.6.520

- `analysis/h_h_residual_persistence_stage1.py` un-skipped (was `.py.skip` since 07-31 when the aggregate signal was weak).
- Ported the v0.6.400a fc_prod-reconstruction patch (applied_layer lookup) — h script had the old `fc_prod = r.get("forecast")` which reads L2 not Production.

## Why h Stage 1 previously failed

"FAIL for weeks" per [[project_07_31_session]] — best guess is pair-log size. Skipped 2026-07-31 with likely <15k h rows; today's fresh run has 32,153 rows. Aggregate signal now lands at +21.41% vs presumably weaker readings in July. Halves stability remains the only blocker.

## Blocker: halves stability — RESOLVED v0.6.522 same day

Morning read: first half −0.93% MAE, second half +3.12% — MARGINAL "sign flip." That reading was a **methodology bug**, not a real halves problem. `/code-review high` on the Stage 1 script exposed three bugs in the shared load path: (1) fc_prod fallback silently dropped to top-level `forecast` (which is L2) when applied_layer+forecast_{applied} missing — contaminating Production baseline; (2) test-window off-by-one so `TEST_WINDOW_DAYS=7` covered 8 dates including 08-23, pulling down aggregate; (3) halves check could crash on n=0. v0.6.522 refactored the harness into `analysis/_residual_persistence_stage1.py` with strict-Production filter + inclusive-last-7-days test window + halves-None guard.

Post-refactor: **h Stage 1 clears STAGE 1 PROMOTE outright.** +24.04% aggregate, 5/5 regime WIN, halves +1.28% / +0.88% (BOTH WIN). Same-session flip from MARGINAL to PROMOTE.

Sibling fields also moved on refactor: dp +21.25% → +28.83%, wg previously-marginal → +36.53% (halves both +14%). The old Stage 1 numbers all three fields were reporting were contaminated by the fc_prod L2-fallback + the test-window off-by-one.

**Stage 2 verified clean of the same class of bugs** (checked same session): Stage 2 scripts use `run_time`-bucketed rolling windows (WIN_A/WIN_B/FULL via `_windows.rolling_windows()`) and read only `forecast_l2` — never Production, never top-level `forecast`. None of the three Stage 1 bugs (fc_prod L2 fallback, test-window off-by-one, halves-crash) apply to Stage 2. The dp/wg Stage 2 curated JSONs the collector reads are NOT contaminated by the class of bugs Stage 1 had. Earlier concern in the v0.6.522 changelog + this memory was overstated and retracted in v0.6.523.

## Next

- **h Stage 2 written same session v0.6.524.** Extracted `analysis/_residual_persistence_stage2.py` shared harness (dp/wg Stage 2 were 408-line cloned siblings); h Stage 2 is a thin wrapper. First-run curated JSON at `weather_collector/data/h_residual_persistence_curated.json`. First-run SKIP cells: pre_frontal/6-11, se_flow/{0-5,6-11,12-23}, sea_breeze/{0-5,12-23,24-47}, sw_flow/0-5.
- **Stage 3 processor bug-fix deployed same session v0.6.525.** `/code-review high` on `wg_residual_persistence.py` template exposed 4 real bugs; fixed in both wg + dp (cloned siblings) before h Stage 3 gets written from them. Bugs: (1) wg telemetry pre/post-clamp mismatch — `per_lead_would_apply` stamped pre-clamp candidate while `new_arr[i] = max(0, ...)` was what landed; fix clamps before stamping. dp doesn't have this bug (dp can be negative). (2) both — `_TABLE_CACHE` never invalidated; fix adds mtime check + `MYWEATHER_REFRESH=1` respect. (3) both — clamp-out silently pooled with normal skips; fix adds explicit `clamped_out_by_band` counter to telemetry payload. (4) both — `no_hourly_array` early return skipped `gate_firing_log.record_firing`; fix records 0/0 before return. Collector deployed 18:11 UTC (revision `myweather-collector-00544-fuj`); 18:17 UTC tick verified new `clamped_out_by_band` key live with expected zeros on nw_flow regime; `table_generated_at` reflects fresh v0.6.524 refit (mtime cache invalidation working).
- **h Stage 2 walker gate starts 08-31.** Needs SHIP-set Jaccard ≥ 0.8 across 7 daily reads per [[feedback_whitelist_promotion_gate]]. Earliest clear ~2026-09-06. On clear, write `weather_collector/processors/h_residual_persistence.py` on the (now bug-fixed) wg/dp template + 7-day live-layer flip gate.
- **Stage 3 processor harness extraction deferred.** Same shared-harness discipline as Stage 1 + Stage 2 would apply, but touches live processors (higher blast radius than analysis-only refactors). Right time to extract is when h Stage 3 would otherwise become the third clone (~09-06). Semantic-preservation gate required (before/after diffs on shadow telemetry).
- **When Stage 2 clean:** wire Stage 3 processor `weather_collector/processors/h_residual_persistence.py` (clone from dp_residual_persistence.py). Ship ENABLED=False + 7-day live-layer gate. Then flip.
- **dp_residual_persistence stays ENABLED=False permanently.** Fixing h routes to dp via Magnus for free. Do not re-open the dp-side gate flip discussion once h ships.
- **se_flow/24-47h evening cluster** — if h Stage 2 picks it up anyway (aggregate does), no follow-up needed. If it doesn't and dp Stage 2 still has cells there, that's the narrow "genuinely can't route through h/t" dp-side exception per updated [[project_dp_is_derived_no_dp_work]] policy.

## Related

[[project_dp_is_derived_no_dp_work]] · [[project_dp_residual_persistence]] · [[project_wg_residual_persistence]] · [[feedback_hypothesis_promotion_pipeline]] · [[feedback_whitelist_promotion_gate]]
