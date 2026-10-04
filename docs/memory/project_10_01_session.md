---
name: project-10-01-session
description: 10-01 digest + verifies. v0.7.19 sr learned_gbm feature-path fix — xr_spread wiring for sr. v0.7.17 + v0.7.18 verifies weather-pending.
metadata:
  node_type: memory
  type: project
  originSessionId: 74a7659c-1484-4905-a27a-29ebad782615
  modified: 2026-10-01T13:19:15.624Z
---

# 10-01 session

## Scheduled verifies

- **P0.1 v0.7.18 learned_gbm firing: FAILED → fixed via v0.7.19.** Pair-log attribution found 45 post-v0.7.18-deploy sr rows (6 of them in covered sw_flow/6-11 cell), ALL stamped `band_pool`, zero `sr_learned_pick_shadow` in tail 50k rows. The classifier has been silently dead since v0.7.15 ship, not just since the 09-30 wholesale-wipe incident. The 09-30 "restore + prevent recurrence" ship (v0.7.18) only addressed the digest overwrite — the underlying feature-path bug was separate and older.
- **P0.2 v0.7.17 wg/nw_flow/12-23h unskip: weather-pending.** Latest obs_day with pairs in this cell is 09-29 (pre-v0.7.17). No post-ship pairs have closed yet. Re-check 10-02.
- **P0.3 v0.7.11 sr × nor_easter L3 bypass: weather-pending.** Latest sr/nor_easter row is 09-28T21:07. Still no nor_easter weather since then.

## v0.7.19 ship (bed134b5)

**Root cause of v0.7.18 silent no-op:** `weather_collector/processors/cross_run_spread.py:29` had `FIELDS = ("t", "wd", "wg", "dp", "h", "pr", "ws")` — sr absent. The v5 fitter (`l1_selector_per_obs_classifier_stage1_v5.py:51`) trained the sr GBM with real `xr_spread` values from the pair-log. At runtime, `_build_learned_features` emitted `xr_spread=None` on every sr call → `_learned_predict` returned `(None, None)` at the first missing feature → selector fell through to `band_pool`. Shadow stamps use the same predict path, which is why `sr_learned_pick_shadow` was ALSO never fired.

**Fix:** three edits to cross_run_spread.py — add "sr" to FIELDS; add `_LIVE_KEYS["sr"] = ("raw_direct_radiation", "direct_radiation")`; relax the stamp gate so missing xr_edges don't skip stamping (`spread` is stamped for all FIELDS, `xr_q` only when the field has curated edges). sr actually DOES have curated edges — verified live: all 55 sr vt entries carry xr_q=Q1..Q5.

**Policy unchanged.** `LEARNED_SELECTOR_SHADOW_ENABLED = True` stays. v0.7.15 already made the live-apply decision; this fix just restores the mechanism that was quietly dead the whole time.

**Post-deploy verify (12:57-13:07 UTC = 08:57-09:07 EDT):**
- ✅ `cross_run_spread` stamps sr for 55 valid-times
- ✅ `_build_learned_features` returns complete feature dicts (zero None) at all tested leads
- ✅ `_LEARNED_CELLS` loads all 5 covered cells
- ⏳ Full attribution verify weather-pending: current 48h forecast is entirely pre_frontal (classifier correctly inert); only 1 post-deploy sr row has closed (lead=0 pre_frontal, correctly band_pool). Need regime rotation to nw_flow/se_flow/sw_flow to see learned_gbm fire.

## Discipline vindicated AGAIN

[[feedback_shipped_flag_verify_effect]] caught this a second time in two sessions. Yesterday it caught the wholesale-overwrite; today it caught the underlying feature-path bug that preceded both v0.7.15 ship and v0.7.18 "fix". The ship-count tally for sr learned_gbm:
1. v0.7.15 (09-29): claimed cells wired live. Attribution check next day: 97 covered-cell rows all `band_pool`. FAILED.
2. v0.7.18 (09-30): restored wiped cells, split v2b/v5 field lists. Attribution check next day: 6 covered-cell rows all `band_pool`, zero shadow stamps ever. FAILED (different cause — feature path).
3. v0.7.19 (10-01): fixed cross_run_spread.py feature path. Mechanism-level verify passes (features complete, cells loaded). Attribution verify still weather-pending.

Pattern: **a classifier can be "shipped" through three different ships before actually firing**. The ship-is-not-the-effect rule is doing real work.

## New feedback memory

- **Feature-path audit after fitter ship.** Before any ship that promotes a learned classifier (GBM, logistic) to runtime use, grep the fitter's feature-build code against runtime's `_build_learned_features` and `cross_run_spread.FIELDS` — verify every feature the fitter trains on has a runtime producer. The fitter and runtime live in different files and drift silently when fields are added. See [[feedback_fitter_vs_runtime_feature_availability]].

## Pending (10-02+)

- v0.7.19 attribution verify when weather rotates into nw_flow/se_flow/sw_flow
- v0.7.17 wg/nw_flow/12-23h verify (needs nw_flow pairs to close in 12-23h band)
- v0.7.11 sr × nor_easter bypass (needs nor_easter weather)

## Digest triage not yet acted on

- Fresh fires (cc +39.9%, h +25.3%, t +15.6% in 3d): all FRESH-not-sustained → wait per fresh-fire-vs-circuit-breaker discipline
- pp ANOMALY (ΔMAE +124.8%): investigate
- wg.l3_nbm HOT: likely v0.7.17 unskip transient; attribution check in 48h
- NBM skip-ADD two-window CONFIRMED: wd/nor_easter/12-23h, wd/nor_easter/24-47h, wg/nor_easter/12-23h — ship-ready
- NBM stale-skip REMOVE: wg/sea_breeze/12-23h, wg/nw_flow/6-11h
- l1_selector_fit_3way PROMOTE (1/7 days gate) — wait
- pr_l2_regime_lead_retro STAGE 1 (1/7 days gate) — wait
