---
name: project-10-09-session
description: "10-09 morning triage. Refitter clean (10/10). cc derived-max Stage 0 edge has reversed (last 4d -29.4%, 7d -7.3%). chp cloud gate now 12 cells off. wdp live cell calm/12-23 still wins overall (-18%) but its older half flipped. regime_runtime present in pair log."
metadata:
  node_type: memory
  type: project
  originSessionId: df4fd109-ce8f-4279-970d-c5080ddba29b
  modified: 2026-10-09T12:05:41.148Z
---

# 10-09 session (morning triage)

- Refitter 08:30Z: 10/10 published, `last_run_ok` True. Selector: 5 overrides, 4 pick changes (h/0-5, h/6-11, h/24-47, dp/6-11 nbm→hrrr). Learned sr cells `pre_frontal/24-47` + `se_flow/12-23` (LIVE_DEMOTED holds).
- chp cloud gate: 12 cells gated off (was 2 called out on 10-08). `nw_flow/6-11` cleared 7/7 as predicted; `pre_frontal/6-11` still 6/7. The digest's stage2_vs_l6 "7 cells lose" WATCH does not read the cloud gate.
- Pair log: `state_fc.regime_runtime` present from obs 10-08 19:07 (1,820 rows by 07:07Z 10-09). Rows joined to pre-deploy snapshots still lack it; full coverage ~10-10 20Z (48h lead). Disagreement vs `regime_synoptic` tiny so far (4 rows/field) — few NBM routes overnight.
- v0.7.33 effect NOT verifiable yet: no sr rows in runtime `nw_flow/12-23` since deploy.
- **cc derived-max (h_cc_sat_guard_stage0) edge reversed:** overall still PROMOTE +44.2%, but last 4d −29.4% (n=432), last 7d −7.3% (n=1741). The overall number is carried by 09-26..10-02 nor'easter/overcast days. Do not advance to SAT_THRESHOLD/selector refit.
- wdp (live cell `calm/12-23` only, frozen in repo since v0.7.30): stage2 verdict changed to HOLD. calm/12-23 composed gate still −18.0% vs L1 (n=429) but firing-row half B (09-09→09-24) now +13.7%. Not acted on. wdp keys on fc regime — another consumer of the [[project_10_08_session]] regime-label mismatch.
- Digest items held: lc_recent_bias ch (streak 1/7, CHURN, cloud gate cleared []); L4 add sr 2/7; blender dp pre_frontal/24-47 STABLE day 1; wg nor_easter/12-23 skip ADD (half A −0.00, same as 10-03 drop); wg.l3_nbm HOT (09-14 precedent); wdp_nbm/chp_nbm DROP (THIN n=25, 08-28 hold); t/production@12-23 +12.2% (stale override tail, rolls off ~10-10).

## Shipped: v0.7.35a (`15dd8285`) — debug page only
- Applicability map in cascade order: L1b › L2 › L3 … specialists › L2_NBM › NBM cascade › C1 last. Static L2/L2_NBM blocks wrapped (`appl-static-L2`, `appl-static-L2_NBM`) and slotted by `renderApplicabilityMap()` via `data-layer-id`.
- Blender status tile moved from Applicability to the L1 section (after the selector); stale "shadow only" badge fixed. Joe confirmed both on the live page.
- Headless test note: the debug page's sequential `load()` never completes in headless Chrome (`--dump-dom` with `--timeout` captures before render; `--virtual-time-budget` hangs). Test renderers in a scratch page built from the real HTML slice + function, fed live `weather_data.json`, using `--virtual-time-budget` (works there).

## Shipped: v0.7.36 (`462ad409`) — learned-selector fitters on regime_runtime (refitter deploy pending)
- `analysis/_cache.RegimeRuntime`: observe(r) every row, get(r) → stamped `regime_runtime`, else rebuilt from the same (run_time, valid_time) pre-swap HRRR wd/ws/t/cc (deepest of forecast_l1r..l1), else `regime_synoptic`. Rebuild = stamped on 130/130 routed t rows.
- v5 (sr) + v2 (t) switched. Backstamped log labels: 960 stamped / 394,840 rebuilt / 5,601 fallback (1.4%).
- Before/after same data: sr cells pre_frontal/24-47 + se_flow/12-23 → + `ne_flow/12-23` (halves +6.0/+17.9, n=1,565). t HOLD both.
- Next moves (one ship each): selector by-regime walker, blender, wdp. Also the v5 FEATURES mismatch: fitter reads post-swap `state_fc` wind/cloud/solar, runtime `_build_learned_features` reads raw `hourly` arrays (forecast_snapshot.py:239).
- Stage 2b: `walkforward_lc_regime` was retired deliberately in v0.6.592 (09-12, "FLAT for weeks"); the pruning missed `walkforward_lc_regime_ship_stability`, which still re-parses the frozen output. Retired in v0.7.37 (`fc5a7304`) at Joe's go; debug-page "decide" item removed. If regime-Lc returns, un-park the walkforward for a fresh read.

## Shipped: v0.7.38 (`5fe1595a`) — debug page full sweep
- Recent activity 10-09 + 10-08 added, 10-06/10-05 trimmed. What's running: new L1 entry; chp (cloud gate) + wdp (1 frozen cell) rewritten; frozen prod-vs-raw % removed (point at live tables). Upcoming rows rewritten (see carry-forward). Post-ship: v0.7.33–36 added; v0.7.7/8/10/12/13/14/15/16 + sr nor_easter watch archived.
- Closed 10-09: "wg calm/24-47 audit gap" — cell is already in `skip_table_nbm_curated.json`; the walkforward lists already-skipped cells (it scores the l3_nbm counterfactual regardless) and `nbm_skip_add_audit` drops them. Same for the sr/wd nor_easter proposals.
- dp blender: `dp/nw_flow/24-47` halves 4.5/39.9 (n=456 7d) → stay shadow. `dp/nw_flow/12-23` SHIP-READY halves 53.0/49.9, n=357 7d / 507 30d (under 400 on 7d; verifier still on old regime label).
- L4 walkforward proposal is now add `sr` (2/7); dp,h dropped out 10-07.

## Carry-forward to 10-10 (in order)
1. **v0.7.36 is LIVE** — Joe deployed refitter rev `00005-qez`; Claude ran it 13:44Z 10-09, 10/10 published. Learned cells `sr/ne_flow/12-23` + `sr/se_flow/12-23`. `pre_frontal/24-47` DROPPED (cloud log: A half held-out +9.63% vs B +20.92%, verdict one-window — fails held-out ≥ 0.5×train-lift; local 07:37 run had A +24.01%). Not yet separated: label change vs ~6h newer data. Check: refresh the backstamped cache, run HEAD~ (pre-v0.7.36) and current v5 on the same file, compare the cell. Also read the 04:30 10-10 fit's cell set. Cloud label counts: 1,224 stamped / 395,312 rebuilt / 5,624 fallback.
2. **regime_runtime migration, next ship:** selector by-regime walker (`l1_selector_by_regime_walker`, a cloud table) onto `_cache.RegimeRuntime` with before/after; then blender fitter + `l1_static_blend_shadow_verify`; then wdp. One ship each. Then scope the learned-feature mismatch (fitter post-swap `state_fc` vs runtime raw `hourly`).
3. Daily reads: t/production@12-23h should be gone (~10-10); cc Stage 0 (edge reversed, stalled); override walkforward day 4; wdp calm/12-23 all-rows lift; chp `pre_frontal/6-11` should hit 7/7 and gate off.
4. Effect verifies waiting on weather: v0.7.33 (sr runtime `nw_flow/12-23` → `band_pool`), v0.7.36 `ne_flow/12-23` paired read after a few ne_flow days.
5. Calendar: ~10-11 ch router re-read; 10-13 TEMPORARY nor_easter skips (wd v0.7.24, sr v0.7.11); ~10-24 backstamp prune (60d).
