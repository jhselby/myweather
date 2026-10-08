---
name: project-10-08-session
description: "10-08 morning. Refitter 04:30 ET run clean (10/10 published, collector serving the 08:30Z tables). t FRESH FIRE = tail of the stale bundled t/12-23 NBM override (runs 10-05 09Z..10-07 08Z), already ended by the cloud refit. chp WATCH 6 cells: 2 already gated off by the cloud gate, 2 at 6/7 lose. sr learned nw_flow/12-23 re-added by the 04:30 fit despite paired -44.2%."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-08T11:00:00.000Z
---

# 10-08 session (morning triage)

## Carry-forward checks
- Refitter 08:30Z: all 10 tables published, `last_run_ok` True. Selector: 1 override, 0 pick changes.
- Collector: the table loader prints `← GCS` only on the first GCS load, not on generation refresh, so there is no log line for the reload. Verified instead via the `fitted_at` 08:30/08:31 stamps in the live `weather_data.json`.
- Collector RSS: warm instance 920–950 MiB across ticks (limit 2048M), deltas +6..+47 MiB. No tracebacks. GoMOFS 503s are NOAA upstream.

## t FRESH FIRE (3d +16.4%) + t/production@12-23h +12% vs raw: explained, no action
- By run_time, t 12-23h `selector_source` was NBM for runs 10-05 09Z → 10-07 08Z (the deploy-frozen bundled table's 7d override, see [[project_10_07_session]]), HRRR before and after.
- Loss sits on those rows: 12-23h 10-06 served 3.76 vs raw 2.60; 10-07 1.56 vs 1.06. Raw HRRR itself was also bad 10-05/10-06 (3.5/3.75), so part of the 3d jump is weather.
- Every cloud fit since 10-07 17:19 picks HRRR for t/12-23 (30d −4.6%, recent +3.3% < 5% override bar). Should roll off the 3d window by ~10-10.

## chp WATCH (stage2_vs_l6, 6 cells)
- The tool does not know the cloud `chp_cell_gate`: `se_flow/12-23` and `sw_flow/0-5` are already gated off.
- `nw_flow/6-11` (+104%) and `pre_frontal/6-11` (+33%) lose 6/7 days; the gate needs 7/7 and will clear them on its own once the win day ages out. `ne_flow/12-23` 5/7. `pre_frontal/0-5` wins all 7 days (Δ −14%; SKIP only on halves).

## sr learned_gbm
- 04:30 fit cells: `nw_flow/12-23`, `pre_frontal/24-47`, `se_flow/12-23`. `sw_flow/0-5` (new 10-07) dropped before it was read.
- `nw_flow/12-23` is back. Paired (served vs `error_l5_nbm`) unchanged since 10-07: −44.2%, n=207 (10-02 +87%, 10-03 −13%, 10-06 −57.5%). Same bar as v0.7.27's `nw_flow/24-47` (−21.5%, n=193).

## Digest daily reads
- `l1_selector_override_walkforward` day 2: all FLAT again (override −1.1%, daily refresh +0.8%, 14d-stale −1.8%; best daily_30d +1.7%).
- `h_cc_sat_guard_stage0` day 3: PROMOTE +47.1%, 18/22 STABLE, but last 4 days +0.7% — the edge has faded in the newest days.

## Shipped: v0.7.33 — sr learned `nw_flow/12-23` demoted
- Added to `LIVE_DEMOTED` in `analysis/l1_learned_selector_curate.py`. Joe deployed the refitter (rev `00004-naq`); Claude ran it at 10:55Z: 10/10 published, learned cells now `sr/pre_frontal/24-47` + `sr/se_flow/12-23`.
- Auto-mode classifier blocks `make deploy-refitter` from Claude; `make run-refitter` is allowed. Don't batch a run with a deploy: on 10-08 the run went through on the old code while the deploy was refused.
- Effect verify (next sw/nw daytime): sr rows in nw_flow/12-23 stamp `selector_mechanism = band_pool`.
