---
name: project-10-05-session
description: "10-05 session (cloud). Shipped v0.7.24 (l3_nbm wd skip ADD: se_flow/24-47 normal + two TEMPORARY nor_easter cells), deployed rev 00609-hey. Triaged the 10-05 digest: L4 add dp,h HELD (window contains the h NBM break; multi-tool gate not met), chp v0.7.9 verify NOT met (6 cells, expected <=1), cc/0-5h C1d escalation condition likely met. Effect of the skip cells NOT yet verified."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-05T15:00:00.000Z
---

# 10-05 session (cloud, repo only; no gcloud creds, no pair-log access)

## Shipped: v0.7.24 — l3_nbm skip ADD for wd (commit `dc1f560`, on main)

- `weather_collector/data/skip_table_nbm_curated.json`: `l3_nbm.wd` += `se_flow 24-48`, `nor_easter 12-24`, `nor_easter 24-48`. Plus history entry (`2026-10-05T08:28`), ship_history entry, note. Version bump `index.html`/`version.json`/`sw.js` -> v0.7.24 (`build.py`), CHANGELOG top entry.
- **`wd/se_flow/24-47`** is a normal two-window CONFIRMED: 14d n=620 -20.00%, 50d n=6,052 -5.60%, halves -0.62/-9.94. With it, l3_nbm is skipped for wd in every se_flow band.
- **`wd/nor_easter/12-23` and `/24-47` are TEMPORARY, RE-REVIEW 2026-10-13.** 14d n=228 -24.70% vs 50d n=270 -24.59% (halves -24.32/-24.70); 14d n=206 -17.70% vs 50d n=208 -17.93% (halves -25.00/-17.75). The 50d window adds only 42 and 2 rows over the 14d, so both windows are ONE event and the two-window gate is not independent confirmation (same circuit-breaker treatment as the v0.7.11 sr nor_easter bypass). See [[feedback_two_window_needs_independent_rows]].
- Dropped from the batch: `wg/nor_easter/12-23` (half A degenerate at -0.00). `wg/nor_easter/24-47` is FRESH (halves +66.7/-10.7), not confirmed. `wg/nw_flow/6-11` REMOVE still held (50d halves).
- Reversible: delete the three entries from the skip table and redeploy. Cells fall back from l3_nbm to l2_nbm for wd.
- **Deploy:** `make deploy-collector` by Joe. Revision **`myweather-collector-00609-hey`, updateTime 2026-10-05T12:33:28Z** (commit stamped 12:28:27Z). Joe merged `dc1f560` into local main BEFORE deploying (the deploy uses `--source=.`, the whole working tree, including the digest-regenerated curated JSONs). Pre-deploy check: `l1_learned_selector_curated.json` had **5 cells** (matches the digest; the 09-30 wipe incident is the reason for this check).
- Post-deploy: ticks 12:57..13:47Z all clean (84-96 s, no NameError/KeyError/AttributeError; start RSS 468 -> 535 MiB, consistent with an instance born at the 12:37Z tick). The 12:37Z first-tick log lines were NOT seen. Pushed to main after the revision check (`e38edbc..dc1f560`).
- **EFFECT NOT YET VERIFIED.** Loader was checked only in-container (`skip_table_nbm.should_skip`: 3 cells skip, `wd/nor_easter/0-5h` and `wg/nor_easter/12-23h` do not). Real proof = pair log once the affected hours close: `wd` rows in those cells should have `applied_layer` = `l2_nbm`, not `l3_nbm`. Note the pair log records counterfactual `error_l3_nbm` regardless of the skip, so the CONFIRMED audit list will not clear by itself.

## 10-05 digest triage (digest run 07:51 EDT; 208/208 OK, nothing in SHIP-ELIGIBLE or Needs attention)

- **L4 add dp,h: HOLD.** Divergence shows "GATE CLEARED (7/7)" but the exec summary says `walkforward_l3l4_validator` is "1/7 days confirmed; only 1 tool-group agreeing (need 2)" => the live-layer gate (7 reads / 2-tool / per-cell / no-ENT) is NOT met. Verdict also now says `[entangled: 1]` (was 0). Validator default test window is 10 days (`--cutoff-days 10.0`), which still contains the 09-30..10-02 h NBM break. A 3-day rerun is regime-fragile (the script's own help) and overwrites `analysis/output/walkforward_l3l4_summary.txt`. Wait until the break leaves the window (~10-13) or a second tool group agrees.
- **chp v0.7.9 verify: NOT MET.** Expected `h_ch_persistence_blend_stage2_vs_l6` WATCH count 4 -> <=1; observed **6** (5 on 10-04), worst `nw_flow/6-11` +52.11%. Caveat: that tool uses a 10-day window with pre-09-28 days still in it, and the 09-21 note says its 10-day numbers inflate magnitude 3-5x ([[project_chp_narrow_to_0_5h_watch]]). Hypothesis (unverified): count falls once the window is fully post-v0.7.9 (~10-08/10-09). Re-check then. `nw_flow/6-11` is not in the 09-28 list of 9 gated cells.
- **cc/0-5h C1d watch (trigger date 10-05): CLOSED, no ship.** `n_low` is 832 and structurally capped (the calibration uses a rolling 14-day window, so it plateaus; every 0-5h/6-11h cell fails the 1000 floor). Today's cc/0-5h row: premium +429.63% (low 7.46 / high 39.49) vs +110% on 09-13; `scripts/c1d_cc05_stability.py` over 21 windows: +145% to +762% (5.3x), halves disagree wildly, but direction positive in every window and half (gap 19 -> 33-37 -> 32.5 pts; prod-error variant +57% to +205%). **`confidence_layer.ENABLED = False`**, so a C1d cell would have no user-visible effect; calibration audit HOLD at 13%. See [[project_cc_0_5h_c1d_watch]] (CLOSED section).
- `decay_tau_tuning` fell back to HOLD (0/3 reads agree, pa/pp only): supports not shipping per-field tau.
- `wg.l3_nbm` NBM sentry HOT (help +10.4% -> -6.6%, n_fresh 2,968). 09-14 precedent ([[project_wg_l3_nbm_sentry_09_14]]): 3-day dip vs a durably earning cell, two-window gate decides; no action.
- New tau-suspect `t/production` (helps 0-5h -22.1%, hurts 6-11h +9.2%); `h/production` tau-suspect persists (12-23h +21.4%). Both probably the same event window; not checked.
- `cc/production` vs raw: improved to +11.4% (0-5h) and +25.1% (6-11h), 12-23h flag gone, BUT only because raw got worse (17.89 -> 21.75 at 0-5h) while production also rose (21.95 -> 24.24). Still unexplained.
- `l1_static_blend_shadow_verify`: curated 16 SHIP-READY / 4 HOLD / 0 KILL (was 14/6/0); h 11/20, dp 9/20. v0.7.21 stamp holds: 0 rows excluded across 87 applied rows (h/calm/24-47 62, h/nw_flow/24-47 24, h/ne_flow/24-47 1). The 62 under "calm" are probably the new sw_flow cell bucketed by the pair-log regime label (inferred, not confirmed).
- `h_pre_front_orthogonality` KILL again (n=16 passages); `pre-frontal` narrow-promote STABLE-EMPTY. No action ([[project_c1e_hsf_kill_investigation]]).
- Stage 2b regime-Lc "READY, 7 days, 16 cells" is still the frozen-file artifact (`walkforward_lc_regime.txt` mtime Sep 12; see [[project_10_04_session]]).
- Debug page `OPEN_WATCHES` is empty: no staleness items.

## NOT done / pending (carry to the next session)
1. Verify the v0.7.24 skip cells took effect (pair-log `applied_layer`, above).
2. **10-13: re-review the two TEMPORARY wd nor_easter cells** (and the sr nor_easter bypass from v0.7.11, same date).
3. L4 add dp,h: wait for the 10-day window to clear the h NBM break, or a second tool group; look at the ENT field.
4. chp WATCH count re-check ~10-08/10-09.
5. ~~cc/0-5h C1d~~ CLOSED 10-05 (see above).
6. ~~Debug page sweep~~ DONE v0.7.25 (10-05): Recent activity 10-05/10-04/10-03, Upcoming rebuilt, blender state (two live cells), watches, C1d row, NBM skip count (22). Verified: tag balance unchanged, `make check-stale` clean, headless Chromium over http shows 3 visible entries. In-flux items carry `[as of 10-05]` markers (v0.7.24 effect, chp recount, cc/production) and need a light re-touch when they resolve.
7. Carried from [[project_10_04_session]]: cc/production unexplained; Lc l6 vs ch se_flow; stale Stage 2b decision; `scripts/ch_v075_live_verdict.py` is on main now; applicability-map registration; `tests/test_layer_tuple_sanity.py`; `c1_calibration_audit` HOLD check. ~10-09 dp/nw_flow/24-47 second look; ~10-11 ch router re-read; 10-13 sr bypass re-review.
8. Cloud sessions cannot read collector logs (`gcloud` has no creds/project); Joe runs `gcloud functions logs read myweather-collector --region=us-east1 --limit=40 --gen2` and `gcloud functions describe myweather-collector --region=us-east1 --gen2 --format="value(serviceConfig.revision,updateTime)"` ([[reference_cloud_session_workflow]]).

## Related
- [[project_10_04_session]] · [[project_10_03_session]] · [[feedback_two_window_needs_independent_rows]] · [[feedback_deploy_sequence]] · [[feedback_auto_curate_wholesale_overwrite]]

## Added later 10-05 (same session)
- **v0.7.25 debug page full sweep** (see item 6). Page and changelog updated; pushed to the working branch.
- **cc/production investigation (code read, no data yet):** Ccd (`cc_from_derivation.py`) runs at `collector.py:607`, AFTER decay_apply (573) and Lc (595) but BEFORE the chp (618) and clp (631) gates; its docstring says "runs LAST, after chp/clp", which is wrong. The snapshot reads cc `l6` = live `cloud_cover` after Ccd, ch `l6` = `cloud_cover_high_post_lc` (pre-chp). Ccd is tick-level: if the tick regime is `se_flow` or `unknown` it no-ops for all 48 leads; leads with raw cc >= 90 keep raw (SAT_THRESHOLD). `h_cc_derivation` defines "production" as cc `forecast_l6` (i.e. Ccd's own output), yet reports derived beating it by +41-43%, and its per-day table shows prod == raw (e.g. 10-05 39.70/39.70): so live cc often equals raw. Unresolved by code reading. `h_cc_composition_pure` says max-overlap composition error is ~1.4 pts, so "cc's damage vs raw is essentially all cascade".
- **Scripts written (branch `claude/relaxed-darwin-7hh03p`, not yet on main unless pushed):** `scripts/c1d_cc05_stability.py` (run, results in the closed watch note) and `scripts/cc_prod_vs_raw.py` (written and synthetic-tested, NOT yet run on the real pair log). It splits live-vs-raw by Ccd changed/unchanged, saturation, regime, applied layer, and tests derived-after-chp (`dmax_p`). Run on the Mac: `git fetch origin claude/relaxed-darwin-7hh03p && git show FETCH_HEAD:scripts/cc_prod_vs_raw.py > scripts/cc_prod_vs_raw.py && python3 scripts/cc_prod_vs_raw.py`.

## cc/production RESOLVED (10-05, later): the sentry line is an artifact; the real finding is selector routing
`scripts/cc_prod_vs_raw.py` run on the Mac (14d, complete cc+cl+cm+ch quads, n=1,938 per band). Numbers (0-5h / 6-11h):
- raw 23.67 / 28.39; **served 20.75 / 26.82** (-12.3% / -5.5% vs raw); **derived-max of cl/cm/ch 13.54 / 15.79**; derived-after-chp 12.91 / 16.07 (the Ccd-before-chp ordering is worth only ~5% at 0-5h, nothing at 6-11h).
- **Applied layer of the served cc: `l2_nbm` on 1,674 of 1,938 (86%) at 0-5h and 1,298 (67%) at 6-11h**; `l1` 190 / 555; `l6` 69 / 85. The selector routes cc to NBM (committed table, fitted 09-13: NBM in all four bands) and `forecast_snapshot.py` overwrites `entry[cc]` with the deepest NBM layer (`l2_nbm` for cc). On `l6`-applied rows served == derived-max in 100% of rows, so **Ccd works as designed**; it is simply not what is served most of the time. On the `l2_nbm` rows: served 19.23 / 22.13 vs derived-max 11.06 / 10.12.
- Derived-max beats served in **every regime** at both bands (e.g. 0-5h calm 11.04 vs 20.73, nw_flow 11.69 vs 19.97, pre_frontal 15.41 vs 23.76, sw_flow 25.55 vs 35.35, se_flow 16.58 vs 17.35).
- **The layer-shape sentry's "cc/production worse than raw" is a lucky-baseline artifact.** Daily 0-5h: served beats raw by 22-48% on cloudy days (09-21..09-25), then +314% on 09-26 (raw MAE 1.91) and raw MAE exactly 0.00 the next day (my script divided by it and crashed). nor_easter rows: raw 0.05/0.00 (saturated overcast) vs served 7.03/9.08.
- **Saturation guard looks wrong in this window:** raw >= 90 keeps raw (`SAT_THRESHOLD`); 61% of 0-5h rows were saturated, raw 24.07 vs derived-max 10.07. The guard was added 08-04 from n=235 rows at obs 95-100.
- **KNOWN_LIVE_PIPELINES mislabels `h_cc_derivation`** ("target already live"), which suppresses its PROMOTE (+43% pooled, halves +35%/+43%). The Ccd flag is live; the served value mostly is not Ccd's.
- **Unresolved:** the committed selector table's cc `hrrr_prod_mae` (22.6/25.2/26.8/27.4 over 30d to 09-13) looks like raw, not Ccd's derived output; why the fitter's HRRR-side candidate is that high is not explained (the table in the repo is stale; the collector's copy is refit daily).
- **Caveats:** one 14-day window containing the 09-30..10-02 event; population limited to complete quads; bands 12-23/24-47 not measured yet; no halves yet (the script now prints them). **Not a ship.** Next (Stage 0 -> cross-cut per [[feedback_hypothesis_promotion_pipeline]]): run `scripts/cc_prod_vs_raw.py --bands 0-5,6-11,12-23,24-47`, then refit the selector for cc with the derived value as a candidate source (or a 3-way), revisit `SAT_THRESHOLD`, fix the registry label.
- Script bug fixed (my division by a zero daily MAE); it now guards that, adds a derived-max column to the daily table, and prints chronological halves.
- Debug page v0.7.25a carries this (Recent activity 10-05 + the Upcoming 'open' row).
