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

## Backstamp prune: NOT needed until ~10-24
- The backstamped file is the only long history (obs from 08-25; live log starts 09-06). 15 tools read it directly, 13 with no window (all history), including the cloud sr learned fitter `l1_selector_per_obs_classifier_stage1_v5`. `nbm_skip_add_audit` / `nbm_skip_earning_audit` need a 50d window from it.
- 694 MB at 44 days (~16 MB/day). Proposed retention 60d (50d audits + margin), implemented in the publisher's appender. Joe agreed to defer; revisit ~10-24.

## `pa` WATCH +598.7%: CLOSED, artifact
- 10-08 anomaly_detector: pa CLEAN (baseline MAE 0.03 in, recent 0.00, −96.4%). The earlier +598.7% was a near-zero dry baseline vs the rainy 09-30..10-02 window. Percent change on a hundredths-of-an-inch base tracks rain/no-rain, not skill. No action.

## `tests/test_layer_tuple_sanity.py`: FIXED (test-only, both failures were stale test)
- Tuple test: extractor capped layer names at 5 chars, so the error-log tuple (with `raw_nbm`, `l2_nbm`…) was never found. Now ≤7 chars, and the comparison ignores `nws` + `*_nbm` (not in the HRRR applied_layer walk).
- Guard test: `l1r` exempted. It holds the selector's live output (forecast_snapshot writes corrected/live arrays), not a shadow array, so there is no ENABLED flag to guard.

## Shipped: v0.7.34 — blender on the applicability map
- `l1_static_blend.describe_applicability()` returned a dict (not the schema's list of layer entries) and was never imported. Rewritten to the schema (`layer_id` "L1b", one entry per curated field: ω, covered vs applied cells) and registered first in `collector.py`'s descriptor loop.
- Collector deployed by Claude (11:27Z; `make deploy-collector` is allowed, `deploy-refitter` is not). The 11:27 tick started before the revision went active, so it ran old code. 11:37 tick clean (cold start +426 MiB), live map 21 layers with L1b: h applied 2/10 (nw_flow/24-47, sw_flow/24-47), dp 0/10.
- Headless Chrome `--dump-dom` on localhost doesn't load the weather JSON, so it can't check the map visually. Renderer unchanged; Joe to eyeball Section D.
