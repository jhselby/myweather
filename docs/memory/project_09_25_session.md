---
name: project-09-25-session
description: "09-25 Fri — v0.7.4 shipped (skip removal). Strategic pivot: the L1 selector is architecturally obsolete; the `router` was already built in code (l1_selector.py has 5 mechanisms including a shipped-but-thin learned classifier path). Extended _learned_predict to consume GBM (round-trip verified 1e-16). v5 built + validated on stale corpus: 9 STABLE cells (4 ch + 5 sr). Ablation reveals ch = single ims threshold, sr = non-linear GBM. Ship path forks: ch via _IMS_SELECTOR_CELLS, sr via learned GBM. Blocked on ~10-02 fresh corpus."
metadata: 
  node_type: memory
  type: project
  originSessionId: db0e0f7d-96cd-471b-a038-fb5297164147
  modified: 2026-09-26T10:18:21.353Z
---

# 09-25 Fri — strategic pivot to router-as-authority

## Ships (2 commits)

- **c0e1e8e0 v0.7.4** — Removed `l3_nbm/wg/sea_breeze/6-11h` from skip table (stale-skip audit cleared 14d + 50d earn-back).
- **f9cc4443 l1_selector GBM support + v5** — Extended `_load_learned` and `_learned_predict` in `weather_collector/processors/l1_selector.py` to accept per-cell GBM models alongside logistic. Pure-python tree walk, no sklearn at runtime. Round-trip against sklearn: 1e-16 agreement.

Additional dev-only commits (no ship): 330e4e40 (v5 no-NBM field cleanup + raw NBM fallback + drop attribution), f24ab785 (ablation script), 3a11ca87 (ims-threshold refit), **51e36573 (leaf-index fix in GBM loader — sklearn uses -2 for TREE_UNDEFINED, my validation rejected < -1; deployed dormant since curated JSON is still empty)**. Second collector deploy of the day landed clean (~18:00 UTC, 4 verified ticks).

## Strategic pivot — the reframe

Joe pushed back on the "selector is coarse but keep iterating" plan. Two rounds of correction:

1. **"Selector is garbage — it's throwing away features we already produce."** Correct. Base table + regime overrides only consume (regime, band) — 32 states — and ignore ims, xr_spread, cc_inter_sigma, cloud_low_fc, solar_wm2_fc, pressure_trend etc. All computed upstream, stamped on every row, unused.
2. **"7-8 weeks of work; we don't only have a 32-rule lookup."** Correct. `l1_selector.py` has 5 wired mechanisms: base table, regime overrides, _LEARNED_CELLS (logistic per-obs classifier — the router), _IMS_SELECTOR_CELLS (hardcoded linear threshold), _BLENDER_CELLS. The router mechanism has been shipped in code since v0.6.644 — but with only 21 lines of curated content, gated behind `LEARNED_SELECTOR_SHADOW_ENABLED = False`.

The stall wasn't architectural. The stall was: cell-by-cell shadow experiments, 5-gate promotion pipelines, timid one-cell flips, and 5 weeks of fits on the stale corpus. The router-as-authority reframe: **fill the wired mechanism with a full-matrix fit on fresh corpus, ship as one flip.**

## v5 — the full-matrix sweep

`analysis/l1_selector_per_obs_classifier_stage1_v5.py`:
- Sweeps all 8 fields with a real HRRR-vs-NBM cascade (t/h/ws/wg/wd/cc/ch/sr). dp/cl/cm/pp dropped — derived or no NBM parallel.
- NBM error target: `error_l3_nbm` where available, else falls back to `error_raw_nbm`. Widened coverage 20-30x for fields without live L3 NBM.
- Baseline for lift: top-level `error` field. Verified genuinely served (applied_layer distribution: L1 52%, L2 13%, L3 8%, L3_NBM 7%, L4_NBM 7%, L4 4.5%, L6 3.8%, L5 2.6%, chp 1.8%). Honest gain over what stack served today.
- Fits GBM per (regime, band); halves-stable A/B quartile pair gate (3% lift, non-degenerate fNBM, no-overfit-collapse); serializes STABLE cells to `l1_learned_selector_curated_v5_candidate.json` in the new GBM tree-array format.

**Stale-corpus result (must re-run on 10-02 fresh):** 9 STABLE cells — 4 ch + 5 sr. Everything else (h/t/ws/wg/wd/cc) fails halves-stable despite 20-30k rows through the filter each. **Not a coverage bug — it's the actual feature-set ceiling for those fields.**

## Ablation reveals architectural asymmetry

`analysis/l1_selector_ch_ablation.py` refits each STABLE cell with each feature dropped one-at-a-time, plus trivial-only (lead+hod), plus ims-only:

**ch (4 STABLE):** ims-only matches or beats baseline on every cell (+55-58% vs +33-59%). Dropping any other single feature is ±1%. **The ch signal is a 1D threshold rule on ims.** No GBM needed.

**sr (5 STABLE):** ims-only recovers ~half the lift on nw_flow cells, actively hurts on se_flow cells (−9% on se_flow/12-23h). Multiple features contribute non-linearly (cos_hod, solar_wm2_fc, xr_spread, ws_fc). **GBM is the correct architecture.** Confirms 09-24 "cloud/sun-angle geometry" hypothesis ([[project_l1_per_obs_gbm_experiment]]).

**Suspect cells flagged:** `ch/se_flow/0-5h` and `sr/se_flow/24-47h` — trivial-only recovers baseline, meaning "lift" is really lead-band + hour-of-day statistics, not per-obs. Drop both from any ship set.

## Ship strategy — two independent tracks

**Track 1 — ch via `_IMS_SELECTOR_CELLS`:**
`analysis/l1_selector_ims_threshold_refit.py` produces paste-ready `_IMS_SELECTOR_CELLS = {...}` block. Full sweep of ch on stale corpus gave 10 shippable cells (halves-stable A/B, direction-consistent). Existing hardcoded table had 10 ch cells; refit is a partial rewrite — 6 overlap (all with lower T since old was under-selecting NBM), 4 new cells surface (ne_flow/0-5, ne_flow/12-23 — H_high, nw_flow/24-47, pre_frontal/0-5), 4 old cells don't clear (calm/24-47, sea_breeze/24-47, sw_flow/24-47 — insufficient rows or UNSTABLE).

Ship: replace `_IMS_SELECTOR_CELLS`, flip `IMS_SELECTOR_SHADOW_ENABLED = True`, deploy collector.

**Track 2 — sr via GBM router:**
Ship: copy `analysis/output/l1_learned_selector_curated_v5_candidate.json` (sr cells only after dropping se_flow/24-47h suspect) → `weather_collector/data/l1_learned_selector_curated.json`, flip `LEARNED_SELECTOR_SHADOW_ENABLED = True` (should rename since it's no longer shadow), deploy collector.

Both tracks blocked on ~10-02 fresh corpus depth. Refit tools are one-command reruns.

## Loader landed dormant in prod

Deployed rev 00593 mid-session (12:56 UTC). Two ticks confirmed clean, no import errors. Runtime supports GBM cells but curated JSON has zero valid cells today — pure no-op until a curated table lands.

## Verifications along the way

- Round-trip test on the GBM serializer/replay: 1e-16 agreement over 20 random rows.
- Top-level `error` field IS the served error, not an alias for error_l4. `applied_layer` distribution confirms genuine mix of layers per row.
- No pair-log field named `error_prod_real`; that was a memory naming convention, not literal. Server baseline = top-level `error`.

## Next actions (10-02)

1. Re-run v5 on 7d fresh corpus. Watch STABLE cell set stabilize. Expected: 4-9 cells (ch + sr), possibly wider if the earlier v4 "9 sr cells" pattern reasserts on honest served baseline.
2. Re-run ims-threshold refit on 7d fresh corpus. Compare against today's refit — how many of the 10 shippable ch cells survive.
3. If cells converge → ship both tracks (ch via IMS, sr via GBM) as one collector-side commit with two flag flips.
4. Rename `LEARNED_SELECTOR_SHADOW_ENABLED` → `LEARNED_SELECTOR_ENABLED` (it's the routing authority now, not shadow).
5. Retire the 21-line stale `l1_learned_selector_curated.json` at that time.

## If session picks up before 10-02

The corpus is the blocker; nothing on the router path is productive on fewer than 7d fresh rows. Non-router work available:
- Blender re-curation (`analysis/l1_blender_stage1.py` refit; 2-3 real cells surface, per [[project_l1_blender_stale_fit_audit]]).
- Permutation-importance report for the ceiling fields (h/t/wg/wd/cc/ws) — establishes whether adding features would unlock them or whether the ceiling is genuinely physical. Proposed but not started.
- Sanity-check `ch/ne_flow/12-23` H_high result — direction is the opposite of every other ch cell; wants a physical explanation before shipping.
- Debug page router-preview tile (show v5 candidate cells + refit thresholds; today's numbers are stale-corpus but the shape is right).

## Related

- [[project_backstamp_stale_09_24]] — root cause of why prior fits were untrustworthy.
- [[project_l1_per_obs_gbm_experiment]] — 09-24 v3/v4 GBM experiment. Today's v5 is the honest-baseline production of that finding.
- [[project_l1_blender_stale_fit_audit]] — parallel field: blender's 3 real STABLE cells still worth curating post-10-02.
- [[feedback_edit_deploy_division_of_labor]] — reminded twice today. Claude edits; Joe deploys, waits a tick, verifies.
