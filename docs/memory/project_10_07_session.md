---
name: project-10-07-session
description: "10-07 session. v0.7.27 shipped (sr learned_gbm nw_flow/24-47 dropped via new LIVE_DEMOTED set; rev 00610-lit, ticks clean, commit cf137375). v0.7.24 se_flow/24-47 skip verified firing via gate_firing_log; nor_easter cells untested. h/t tau-suspect traced to the selector's 7d recency override + deploy-gated table. New digest tool l1_selector_override_walkforward. Found pair-log duplicate rows (live + backstamped overlap 09-06..09-24, 184k exact dups) double-counted by 18 fitters."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-07T14:30:00.000Z
---

# 10-07 session

## Shipped: v0.7.27 — drop sr learned_gbm `nw_flow/24-47`
- Commit `cf137375`. Deployed rev `myweather-collector-00610-lit` 11:51Z; 8 ticks 11:57–13:07Z clean (no tracebacks, RSS 472→545 MiB, same pattern as 10-05). GoMOFS 502s on 13:07 = NOAA upstream, buoy fallback worked.
- **Correct measure is PAIRED:** on `learned_gbm` rows, served (`prod_error`) vs `error_l5_nbm` (what `band_pool` serves for sr) on the SAME rows. The 10-06 read compared learned rows to band_pool rows (different hours, different day/night mix) and was wrong.
- Paired 7d: nw_flow/24-47 **−21.5%** (38.45 vs 31.65, n=193; lost 10-05 and 10-06) → dropped. nw_flow/12-23 **−44.2%** (n=207, almost all from 10-06: 76.0 vs 48.3; halves +1.2/−57.8) → **held, recheck 10-08**. se_flow/12-23 +9.9%, se_flow/24-47 +5.9%, sw_flow/6-11 +3.0% (10-06 had reported +9..+31%).
- **`LIVE_DEMOTED` set in `analysis/l1_learned_selector_curate.py`** — the v5 fitter keeps emitting the cell STABLE (+12/+29% held-out) because its baseline is served `error`, which on live rows is the classifier's own pick ([[feedback_apply_flip_invalidates_shadow_verifier]]). Without the set the next digest re-adds it ([[feedback_auto_curate_wholesale_overwrite]]).
- Effect verify: from 10-08, sr rows in nw_flow/24-47 should stamp `selector_mechanism = band_pool`.

## v0.7.24 wd skip verify
- **`se_flow/24-47` CONFIRMED firing:** the only post-deploy se_flow tick (10-07 08:58) shows wd L3_NBM fires 0 / skips 46 (pre-deploy se_flow tick 10-03 18:58: 22/24).
- **nor_easter/12-23, /24-47 UNTESTED:** no nor_easter tick since the 10-05 deploy (post-deploy ticks: nw_flow 211, pre_frontal 41, calm 21, sw_flow 13, frontal 4, se_flow 1). They reach the 10-13 re-review unexercised unless one occurs.
- Method: [[feedback_verify_nbm_skip_via_gate_firing_log]] — the 10-05 note's pair-log method is wrong.

## h/t τ-suspect: 7d recency override + deploy-gated selector table
- Split by `selector_source`: the loss is entirely on NBM-picked rows (h 12-23h: served 6.26 vs HRRR-L2 2.43, n=531; t 6-11h: 1.81 vs 1.01, n=195). On HRRR rows `l2` and `l4` serve identical values — the 10-06 "l2_nbm/l4/l2 split" was partly a label artifact.
- Replaying `l1_selector_fit`'s rule each morning reproduces the observed flips: **every NBM period in both cells was the 7d override** (t: 30d HRRR every day; h: 30d lift +0.5..+3.1%, under the 3% bar). h's override caught a real NBM edge 09-26..28 then held through the 09-30 NBM humidity break; t's override fired twice on small margins (+10.8%, +6.9%) and NBM lost 4 of 6 days.
- **The runtime selector table changes only on deploy.** `l1_selector._load` reads only the bundled `weather_collector/data/l1_selector_table_curated.json`; the only writer is `analysis/l1_selector_fit.py` (digest, Mac). Flip times match deploy mornings. The 10-05 note's "the collector's copy is refit daily" is WRONG.
- h's alert should fade as 09-29..10-01 rows leave the 7d window (~10-09); t's NBM periods leave ~10-10.

## New digest tool: `analysis/l1_selector_override_walkforward.py` (commit `fa8b4e2c`)
- Replays the fit rule per morning and scores next-day rows for: actual, always-HRRR/NBM, 30d-only, 30d+7d5 (current), 30d+14d5, 30d+7d10, 14d-only, and the current rule with the table frozen 7/14 days. Dedups the two logs.
- First read (14 run days 09-24..10-07, halves at 10-01): override **−1.3%** vs 30d-only (halves −0.2/−3.5; mostly cc +11.0 vs +2.9 and t +2.3 vs −0.5; helps h −0.5 vs −2.1); daily refresh **+0.6%** vs deploy-frozen; 14d-stale table **−1.8%** vs daily (sr −17.3%, dp −6.5%); best `daily_30d` +1.8% (halves +0.3/+3.9). **All FLAT** under the both-halves ≥1% rule. Frozen policies use partial 30d windows until 10-08 (log starts 08-25).
- **Joe's requirement (10-07):** whatever change comes out of this must run automatically in the cloud — no runtime behavior may depend on the digest being run. A move to daily refit means a cloud-scheduled fit (the collector is already ~545 MiB RSS, so probably not inside the collector), with the bundled table as fallback. Decide only after the tool's verdict holds over ~7 daily reads.

## Pair-log duplicate rows (found, NOT fixed)
- Live `forecast_error_log.jsonl` (obs from 09-06) and `forecast_error_log_backstamped.jsonl` (obs 08-25..09-24) overlap: **184,475 exact duplicate rows** on (field, run_time, lead_h) (t sample: 11,409 identical, 0 differ). `_cache.pair_log_paths()` docstring claims the corpora are disjoint; false since the 09-24 backstamp append ([[project_backstamp_stale_09_24]]).
- **18 analysis scripts** stream both files without dedup, including `l1_selector_fit.py` (writes the shipped selector table): 09-07..09-24 counts twice in its current 30d window. Proposed fix (one place): dedup in `_cache` (e.g. filter the cached backstamped copy to rows with obs_time before the live log's first obs_time). Ages out on its own around 10-24.

## Digest triage (06:07 run, 209/209 OK) — summary
No SHIP-ELIGIBLE, no new kills. L4 walkforward now wants add h,sr (dp dropped; streak reset 1/7) → "L4 add dp,h" carried item is dead. wg nor_easter/12-23 "CONFIRMED" still degenerate half A. New `l3_nbm wg calm 24-47h −110.9% n=635` in the walkforward list but missing from the two-window audit (only 5 of 11 proposals audited) — unexplained. cc Stage 0 day 3 PROMOTE +41.1% but recency last-4d −14.1%. chp stage2_vs_l6 still 6 cells (worst nw_flow/6-11 +104%). dp 7d prod 2.30 vs NBM raw 1.49 / prior 1.53 — the digest tail shows per_field_scoring's 12h window, not 7d; attributed (hypothesis) to the h NBM break via dp = f(t,h). Flips that have flickered before: Lc W=7d, diurnal τ PROMOTE, Lsr PROMOTE (CHURN), l3_nbm regime "B".

## Carry forward
1. **10-08:** sr nw_flow/12-23 paired recheck (drop via `LIVE_DEMOTED` if still negative); v0.7.27 effect (band_pool on nw_flow/24-47).
2. Read `l1_selector_override_walkforward` daily; no selector change until ~7 consistent reads; any change must be cloud-automatic.
3. Pair-log dedup fix (above) — Joe to decide.
4. Carried from 10-06: chp recheck ~10-08/09; 10-13 TEMPORARY nor_easter re-reviews (wd v0.7.24 untested, sr v0.7.11); cc Stage 0 day 4+; applicability-map registration; `tests/test_layer_tuple_sanity.py`; wg calm 24-47 audit gap.

Related: [[project_10_06_session]] · [[project_selector_recency_override_watch]] · [[feedback_tau_suspect_can_be_selector_artifact]]

## Later 10-07: refitter live (v0.7.28 + v0.7.29), backstamp appender fixed
- **Joe's rule:** tables meant to refit on their own must refit in the cloud; the model must never need the Mac digest to work. Ship decisions (skip tables, APPLIED_CELLS, LIVE_DEMOTED) stay in the repo.
- **`myweather-refitter`** Cloud Function (gen2, 4 GB, 2 vCPU, 1800 s, daily 04:30 ET via `myweather-refitter-schedule`, invoker SA `myweather-collector@`). `refitter/tables.py` registry: `l1_selector_table_curated.json`, `l3_nbm_curated.json`, `l4_nbm_curated.json`. Runs the unchanged analysis fitters, guards (structure via each processor's `validate_table`, ≥50% of previous rows, floor, newer fitted_at), publishes `runtime_tables/<name>` + `runtime_tables/history/<date>/<name>` + `runtime_tables/_status.json`.
- **Collector:** `weather_collector/runtime_tables.py` — GCS copy (generation check every 10 min), last-good, bundled fallback. Selector + L3/L4_NBM read through it. L3/L4_NBM 7-day stale rule now re-checked per call (was import-only).
- **Verified live:** refitter run 15:08Z all 3 published; collector rev `00612-rad`, first tick 15:27Z loads all 3 from GCS, clean (105 s; first-tick RSS delta +536 MiB vs ~+420 on earlier first ticks — watch).
- **Backstamp appender** (publisher): frozen since 09-24 (off-by-one offset + daily prune). Fixed `3ccff999` + NameError `186166ae` (my loop rewrite left a stale line; first fix crashed on the 15:00Z run). Publisher rev `00034-geg`: 15:07 run appended 64 MB, file now to obs 09-28; ~3 more hourly runs to catch up. Test appender changes by running `main()` against a fake bucket, not a copy of the loop.
- **Deploys:** 10-07 Joe asked Claude to run the deploys itself ("can't you do it all?") — publisher, refitter, collector all deployed by Claude with gcloud.
- **Next tables to move:** inventory in this session: ~27 runtime files are digest-refit and bundled. Classify each (self-refit vs ship decision) and move the self-refit ones (Lc, Lsr bias tables, residual-persistence curated tables, c1 tables, learned/blender curate) the same way. Also: the backstamp file is append-only and grows forever — prune it like the live log.

## Later 10-07: v0.7.30 — all self-refitting live tables in the cloud (commit 45282892)
- Joe's call: churning Stage 1/2 cell sets are **ship decisions**. Frozen at the copies live since today's deploy: `ch_persistence_gate_curated`, `wd_persistence_gate_curated`, `wg_residual_persistence_curated`, `wg_l3_asymmetric_skip_curated`. Their tools write `analysis/output/candidates/` (`analysis/_candidates.py`); `whitelist_streak` + wg residual walker read candidates. To ship a new set: copy candidate over, bump, deploy.
- Refitter now owns 10 tables: selector, L3/L4_NBM, Lc fit, Lc recent-bias gate, Lsr bias, sr sea-breeze, chp cell gate (chain stage2_vs_l6 → gate), regime walker (by_regime → 3way → walker), learned sr (v2 → v5 → curate). Histories in `runtime_tables/state/`, saved only on publish. Refused tables are put back so later entries read the live copy. `REFITTER_DRY_RUN=1` uploads nothing (test in a scratch copy of the repo — the fitters write histories). Memory 8 GB; run ~7 min.
- Off/shadow layers left bundled (c1, cc combine, clp, dp/h residual, blender, Lsr recent-bias gate, ws tables).
- **Learned sr changed on first cloud fit:** 4 cells → `se_flow/12-23`, `sw_flow/0-5`. The previous 4 were fit on backstamp data frozen at 09-24 (appender bug); cloud fit sees data to 10-05. `nw_flow/12-23` dropped by the fit itself, so the 10-08 LIVE_DEMOTED recheck is moot. **New cell `sw_flow/0-5` needs a paired read (served vs error_l5_nbm) after a few sw_flow days.**
- Collector 17:37Z tick: 9 tables ← GCS (chp gate loads lazily, not hit that tick), RSS +409 MiB, clean.
- Schedule confirmed with Joe: stays 04:30 ET daily. Reference note: [[project_cloud_refitter]]. Rule: [[feedback_self_refit_tables_run_in_cloud]].

## End of 10-07 — carry forward (supersedes the list above)
1. **10-08 morning:** `runtime_tables/_status.json` shows the 04:30 ET run with all 10 published and `last_run_ok` True; collector log shows `← GCS` lines with the new stamps (chp gate once a tick reaches it).
2. Backstamp appender caught up to the current date? HWM last seen 10-05T04:07 at offset 510,473,670. Then check whether the live/backstamped overlap (dup bug above) grew now that the appender runs past 09-24. The dedup fix is still Joe's call.
3. Collector RSS on the first ticks (+409..+536 MiB).
4. New learned cell `sr/sw_flow/0-5`: paired read (served vs `error_l5_nbm`) after a few sw_flow days. v0.7.27 effect: `nw_flow/24-47` rows stamp `band_pool`.
5. `l1_selector_override_walkforward` daily read (day 2 on 10-08). The selector is now refit daily in the cloud, so the "daily refresh vs deploy-frozen" question is settled. The 7d override question is still open.
6. Prune the backstamp file (append-only, grows forever).
7. Carried: chp recheck ~10-08/09; 10-13 re-review of TEMPORARY nor_easter skips (wd v0.7.24, sr v0.7.11); cc Stage 0; applicability-map registration; `tests/test_layer_tuple_sanity.py` (2 failures); wg calm 24-47 audit gap.
