---
name: project-10-04-session
description: "10-04 session (cloud). v0.7.23 committed (4aa17f6). Triaged the 10-04 digest against the checklist. v0.7.5 ch verdict DONE: keep ON, router lift is +15.9% vs always-HRRR (NOT the fit-time +37-76%, which was vs raw L1). Stage 2b regime-Lc gate CONFIRMED stale (input file frozen since 09-12). se_flow Lc question open."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-05T00:00:00.000Z
---

# 10-04 session (cloud session, repo only, no pair-log access)

## State at session end

- **v0.7.23 is COMMITTED and pushed**: `4aa17f6` on main. Closes the 10-03 "deployed but uncommitted" item. `index.html` reads v0.7.23, `APPLIED_CELLS = {"h": {nw_flow/24-47, sw_flow/24-47}}`.
- The memory snapshot `69b37ac` (docs/memory, 402 files) is on main.
- **`scripts/ch_v075_live_verdict.py` exists on branch `claude/relaxed-darwin-7hh03p` only** (not on main). Joe pulled it into an *untracked* `scripts/` copy on the Mac with `git show FETCH_HEAD:scripts/ch_v075_live_verdict.py > scripts/ch_v075_live_verdict.py`. Decide whether to commit it. It needs `analysis/_cache.py` + `analysis/_prod.py` and the live pair-log cache (`MYWEATHER_REFRESH=1` to force a re-download).
- Collector deploy: nothing new this session. Live rev still `00608-jot`.

## v0.7.5 ch verdict — DONE (was the slipped 10-03 KEY DATE)

**Verdict: keep ON for all 10 cells. Re-read ~10-11 on post-event data.** Window 09-27..10-04, n=1713 rows in the 10 cells (`selector_mechanism == ims_threshold`, `field == ch`).

| Measure | MAE | router lift vs it |
|---|---|---|
| router pick | 11.66 | — |
| source it did not pick | 16.62 | **+29.8%** |
| always-HRRR (`error_l4`) | 13.87 | **+15.9%** ← the honest router number |
| always-NBM | 14.42 | |
| prod (`error_{applied_layer}`) | 11.70 | ≈ picked, so users see the pick |
| raw L1 (`error_l1`) | 33.85 | +65.5% (cascade + router, not router alone) |

- Router beat its inverse every day except 10-04 (near tie). The `ims` signal is real.
- **Cells (my thresholds: THIN n<30; FAILING vs best fixed < -5% or picked >= other; HOLDING vs best >= 0 and both halves beat the unchosen source):**
  - HOLDING (n=972, 57% of rows): `nw_flow/24-47`, `pre_frontal/12-23`, `sw_flow/12-23`.
  - MARGINAL: `ne_flow/0-5`, `pre_frontal/0-5`, `pre_frontal/6-11`.
  - FAILING: `ne_flow/12-23` (n=112, -9.8% vs inverse: it picks NBM when ims<4.5, where the two sources agree and the pick carries no information) and the three `se_flow` cells (n=60-119; lose to always-HRRR by 12/64/49% on 6-11/12-23/24-47).
- **Contamination:** 09-30..10-02 = 1,058 of 2,078 rows (51%), a high-error event for every source (HRRR daily MAE 9.1 / 23.8 / 22.6). The failing cells are the low-n ones. **Decision rule (my recommendation, Joe's call):** at the ~10-11 re-read, pull any cell still losing to always-HRRR at n >= 150 on post-event data. That is a cell removal = a ship.
- Rollback if ever needed: flip `IMS_SELECTOR_SHADOW_ENABLED` to False in `l1_selector.py`; the cells stay inert.
- 365 rows landed off-cell (pair-log `state_fc` regime differs from the runtime regime the router used; top: calm/12-23, calm/24-47, nor_easter/0-5). Known mismatch, not a bug.

### The fit-time lift (+37% to +76%) was NOT the router's

`l1_selector_per_obs_classifier_stage1_v5.py` and `l1_selector_ims_threshold_refit.py` take `err_served = r.get("error")` as the baseline. Top-level `error` is the **L2 residual by design** (`forecast_snapshot.py:246-249`); for ch (and cc/cl/cm) L2 == L1, so the baseline was **raw L1**. The fit compared `error_l4` / `error_l3_nbm` against raw L1, so most of the "lift" is the L3/L4 cascade, which runs with or without the router. Verified in code and by the ladder: HRRR-picked rows had `l2` MAE 23.89 == "served" 23.89. See [[feedback_fit_baseline_is_toplevel_error]].

### Layer ladder (HRRR-picked rows, n=1267): l1 24.19 → l2 23.89 → l3 14.47 → l4 11.15 → l6 11.31 → chp 11.44. NBM-picked (n=446): raw_nbm 15.03 → l2_nbm 14.70 → l3_nbm 13.13 → l4_nbm 12.45 (all applied l4_nbm).
- Overall l6/chp add only +0.16/+0.29 over l4. chp helps in `pre_frontal/0-5`, `pre_frontal/12-23`, `ne_flow/0-5` (prod beats picked).

### Open: Lc `l6` appears to hurt ch in `se_flow` (live window) — UNRESOLVED
- `se_flow` cells: prod 21.28 / 22.35 / 14.02 vs picked 17.42 / 15.59 / 12.07 vs always-HRRR(l4) 10.65 / 10.46 / 10.77. Ladder `l4 -> l6`: 10.65->17.27, 10.46->18.73, 10.77->14.70.
- Code facts: ch Lc is a **pooled, forecast-value-binned shift, regime-blind** (`lc_correction_table.json`, repo copy dated 09-13: 20-50 -> -25.3, 50-80 -> -46.3, 80-95 -> -61.4; 0-5 and 5-20 SKIP). `_CELL_SKIP` is empty; `_FIELD_SKIP = {cl, cc}`. The `(field, regime, bin)` skip shape is supported but unused for ch.
- Weak counter-evidence: `analysis/output/walkforward_lc_regime.txt` row `ch se_flow 20-50 n=647`: raw 33.86 / pooled-Lc 15.06 / regime-Lc 16.47 (-9.36% vs pooled). Pooled Lc helped ~55% vs raw and a regime swap would have lost. Column order inferred from the `cm` row; **the file is from the 09-02..09-12 window (frozen, see below)**, and "raw" may be L1, not L4. So it does not cover the live window.
- NBM is also poor in se_flow (25.15, 27.58 in two cells) and the router picks it 26-33% of the time. The split between the two causes is not measured.
- Next step if pursued: pair-log test of `error_l4` vs `error_l6` by Lc bin within `se_flow` for ch. Do NOT change `_CELL_SKIP` on the current evidence.

## CONFIRMED stale gate: Stage 2b regime-Lc "READY" is vacuous

- **Verified 10-05:** `analysis/output/walkforward_lc_regime.txt` has mtime **Sep 12 06:10** (3,977 bytes). Train = 20 days < 2026-09-02, test = 11 days >= 2026-09-02 (so test window ~09-02..09-12). Nothing has rewritten it since.
- Cause: `walkforward_lc_regime` is `.skip.py` and is not among the 208 scripts the digest runs. `walkforward_lc_regime_ship_stability` keeps re-parsing the frozen file; digest 10-04 showed READY "8 days stable, 16 SHIP cells", exactly 16 every day 09-27..10-04. The committed history last changed on 09-13 (16 cells), which matches the freeze.
- Consequences: (1) the Stage 2b "READY" has carried no information since 09-13; Stage 3 (regime-Lc wire, still unwired in the repo) must NOT be justified by it. (2) Every row in that file, including the `ch se_flow 20-50` row (raw 33.86 / pooled 15.06 / regime 16.47), is from the 09-02..09-12 test window: it predates the 09-30..10-02 event and the router era, so it is **weak counter-evidence** against the live `se_flow` Lc observation, not a contradiction.
- Fix options (Joe's call, not done): un-park the script (rename `.skip.py` -> `.py`; check its runtime and `--cutoff-days` defaults first) so the digest regenerates it, or stop reading Stage 2b as a gate. Un-parking would change the digest's script count and runtime.
- The `.skip.py` name predates this session; why it was parked is not recorded in memory (the file was first committed under that name in `07a2907`, v0.6.640, 09-19).

## 10-04 digest triage (digest run 06:36 EDT 10-04, 208/208 OK, no kills, no post-ship watches, regression + NBM sentries clean)

Triaged after reading memory (my first pass was done without it and was wrong on several points — see below).

- **L4 add of `dp`,`h`: GATED 6/7, clears on the 10-05 run.** Do a contamination check BEFORE shipping: the window includes the h NBM break (09-30..10-02). Hypothesis (unverified): the walkforward measured over that window. Read `h_l4_add_candidates.json` / the validator window first.
- **`decay_tau_tuning` "IMPLEMENT PER-FIELD τ" (pa, pp, ws, 3/3): DO NOT SHIP.** `decay_fit.py:151` records reverts: ws 07-02, pa 07-19, h 09-20 (same long-lead regression each time); pp already live at 28. The streak counts set membership, not the τ value ([[feedback_tau_streak_gate_limits]]). Aggregate-only tool; needs the regime x lead cross-cut.
- `h_lsr_recent_bias_gate` "PROMOTE sr": streak 1/7, CHURN. lsr_recent_bias_gate is in Settled/CLEAN. Not an action.
- `h_depression_cloud_confidence_c1_stage2` NARROW PROMOTE (cl): Q1 and Q4 levels THIN (1108/0, 83/39); one measurable level (Q23 1.48). Flipped from REDUNDANT yesterday. Noise.
- **NBM skip pass:** 4 two-window CONFIRMED ADDs. Ship the three `wd` cells (`nor_easter/12-23`, `se_flow/24-47`, `nor_easter/24-47`); **drop `wg/nor_easter/12-23`** (half A degenerate at -0.00). No REMOVE: `wg/nw_flow/6-11` fails halves a 3rd day (50d 2nd half +2.80% vs +3.00% bar, 14d +14.5%).
- **`h` τ-suspect line and the h fire = the NBM humidity break** (same event; receding). Not an independent problem.
- `pa` WATCH improving: +598.7% (10-03) -> +192.3% (10-04), on tiny absolute MAE (0.02->0.05). `pp` WATCH +66.7% (13.0->21.7), bin shift 25.8pp; was ANOMALY improving +177.7->+125.0 on 10-03.
- `c1_calibration_audit` HOLD: 3/23 calibrated, 20 drifted, 13.04% pass vs 75% bar (61.36% on 06-29). `confidence_layer.ENABLED` was False per the 06-29 memory. Not checked whether this is a known standing item or whether ENABLED changed.
- `l1_static_blend_shadow_verify`: v0.7.21 verified clean (0 excluded for missing counterfactual). It listed the applied cell as `h/ne_flow/24-47` (1 row) because it buckets by the pair-log regime (comment at `l1_static_blend_shadow_verify.py:122-126`), not the runtime regime. Still needs a pair-log refresh for the real live verify.
- `lc_fit`, `h_cc_derivation`, etc. in the digest's KNOWN_LIVE_PIPELINES list are live targets, not queue items.

### UNEXPLAINED, no memory or debug-page note: `cc/production` is WORSE than raw in all three bands
- 0-5h +22.7% (raw 17.89, prod 21.95, n=829); 6-11h +41.2% (17.80 vs 25.14, n=1008); 12-23h +14.3% (18.28 vs 20.89, n=2016).
- cc is derived: `cc_from_derivation` overwrites `cloud_cover` with max(cl_l6, cm_l6, ch_l6) except in SKIP_REGIMES {se_flow, unknown} ([[project_cc_is_blend_of_clchcm]]). Start with the components (cl has WATCH ΔMAE -41.7%, 30.5pp bin shift). Persistence-skill shows cc Prod +0.37 vs L4 +0.07, so the two measures disagree; check whether "prod" in the layer-shape sentry uses `prod_error`.
- Debug page grep for "cc/production" found no note. Not yet investigated beyond that.

## My errors this session (so the next one does not repeat them)
1. First digest triage was done WITHOUT loading memory and misjudged: called the h τ-suspect a separate conflict (it is the NBM break), called per-field τ shippable-looking (it has been reverted 3 times), called `lsr` and `wg/nw_flow/6-11` new (settled / carried).
2. Scored the ch verdict with top-level `error` as "served" and concluded downstream layers add error. Wrong: `error` is L2. Fixed by switching to `prod_error()` ([[feedback_top_level_forecast_is_l2]]).
3. Predicted the realized vs-L1 lift would fall below the fit-time lift. It did not (+65.5% overall, +16.8..+95% per cell); that lift just was not the router's.

## Next session (Mon 10-05), in order
1. **Load memory + the digest triage checklist BEFORE reading the digest** ([[feedback_digest_triage_discipline]]).
2. 10-05 digest: **L4 add dp,h** reaches 7/7 -> contamination check first. Also scheduled for 10-05: **v0.7.9 chp 7d verify** (`h_ch_persistence_blend_stage2_vs_l6` WATCH count should fall 4 -> <=1) and the **cc/0-5h C1d watch** (escalate only if `n_low` still < 1000).
3. Decide the stale Stage 2b gate (confirmed frozen since 09-12): un-park `walkforward_lc_regime` or drop the READY claim. Do not wire Stage 3 on it.
4. **v0.7.20/21 live verify** with a refreshed pair log: `h_preempted_source_shadow` (expect `nbm`) + `hourly.corrected_humidity` writeback; both applied cells (`nw_flow/24-47`, `sw_flow/24-47`) should now have rows.
5. Ship the 3 `wd` NBM skip-ADD cells (drop `wg/nor_easter/12-23`).
6. `cc/production` vs raw (unexplained, above).
7. ~10-06 sr GBM Value Captured 7d read. ~10-09 `dp/nw_flow/24-47` second look. **~10-11 ch router re-read** (rule above). 10-13 sr bypass re-review.
8. Still carried: blender applicability-map registration (`describe_applicability` imported nowhere); `tests/test_layer_tuple_sanity.py` failures (`l1r` has no ENABLED guard in `_derive_applied_layer`, bisected, pre-existing); `c1_calibration_audit` HOLD status check.

## Related
- [[project_10_03_session]] · [[project_router_as_authority_pivot]] · [[project_l1_static_blend_v076]] · [[feedback_apply_flip_invalidates_shadow_verifier]]
- [[feedback_top_level_forecast_is_l2]] · [[feedback_fit_baseline_is_toplevel_error]] · [[reference_cloud_session_workflow]] · [[project_lc_regime_conditional]]
