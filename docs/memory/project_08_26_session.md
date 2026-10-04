---
name: 08-26-session
description: "Aug 26 Wed — full-day session. v0.6.490 → v0.6.500 (11 versions). NBM cascade reached ARCHITECTURAL PARITY with HRRR via native L2 for all 8 NBM-scope fields (v0.6.499). Skip-table first-real-pass added 9 evidence-graded cells; selector refit flipped wd 12-23h to NBM. Coach's table measurement-honest via paired-pool math. Notable Calls + High-Conf wired live. Parity definition settled: architecture only."
metadata: 
  node_type: memory
  type: project
  originSessionId: f98aaa56-0f4c-4ee8-a7d4-432f6e02dd1f
  modified: 2026-08-26T17:35:51.986Z
---

Continuation of [[project_08_25_evening_session]]. The big arc: took NBM from "structurally symmetric but built on a v1 shortcut" to real architectural parity, plus finished the coach's-table measurement discipline Joe called out in his 08-26 morning review.

## Key ships (chronological)

**v0.6.490 morning cleanup batch:**
- Recent activity trimmed to rolling 3-day window per debug page's own rule.
- 4 warmup NBM fit-status tiles deleted (L3/L4/L5/L6 fit tiles) + NBM ingester infra tile + NBM skip-table tile. All moved from L1 section to their respective layer sections first, then Joe pointed out they were transient warmup UI regardless — deleted entirely.
- dp/cc rows removed from per-field diagnostic table (derived fields, no independent skill to score).

**v0.6.491 applicability map cleanup + parity callout rewrite:**
- Retired L1 router hand-curated block (dead code doc from v0.6.437).
- Added L2_NBM hand-curated block (originally described the delta-transfer assumption honestly).
- Parity callout in Current State rewritten from marketing-slogan ("STRUCTURAL PARITY") to honest gap enumeration.

**v0.6.492 — coach's table measurement consistency (P0):**
- `analysis/per_field_scoring.py`: new `hrrr_prod_paired` + `nbm_prod_paired` buckets populated only inside `pool_ok` intersection. Emits `hrrr_pipeline_skill_paired_pct` + `nbm_pipeline_skill_paired_pct`. Hit Rate + Value Captured now also gated on `pool_ok`. All 5 coach's-table columns describe the same row set.
- Frontend reads paired fields; footer rewritten to describe shared pool. Causal chaining is now meaningful.

**v0.6.493 — L2_NBM audit + selective delta skip:**
- New `analysis/nbm_l2_delta_audit.py` — grades HRRR-delta transfer per (field, lead-band) on 30d pool. Ships JSON to GCS via publisher. Rendered as "🔍 L2_NBM soundness" tile in Applicability map.
- Finding: 2 halves-agreed wins (wd 0-5h +10.0%, ch 0-5h +3.5%), 1 catastrophic loss (h 0-5h −29% halves-agreed), pooled hurts h −5.4% / dp −4.9% / sr −2.9%.
- Shipped `_L2_NBM_DELTA_SKIP = {h, dp, sr}` in `forecast_snapshot.py` — those fields stamp `l2_nbm = raw_nbm` identity.

**v0.6.494 — Notable Calls + High-Conf tiles wired live:**
- Added `per_band` block to per_field_scoring.json. Per-(field, lead-band) Total Lift under Public Baseline rule.
- Notable Calls: top-1 win + top-3 losses filtered by n≥200 and DERIVED_EXCLUDE + NON_MAE_EXCLUDE. Today's worst-3 all sr (24-47 −40.88%, 0-5 −35.05%, 6-11 −21.39%); best: ch 0-5h +70.55%.
- High-Conf cells: |lift|≥10% AND parent field's halves_agree. Uses field-level halves_agree as per-cell confidence proxy (per-cell halves is future work).

**v0.6.495 — current-config counterfactual scoring:**
- `_DISABLED_LAYER_KEYS = {error_l5_nbm, error_l6_nbm}` — NBM-side only. `_prod_error_current_config` walks the applied cascade skipping disabled stamps.
- New JSON fields: `total_current_config_pct`, per-band `total_current_config_pct` + `prod_cc_mae` + `n_prod_cc`.
- Coach's table: 🪦 cfg X% subscript when |Δ| ≥ 3%. Notable Calls scored on current-config lift.
- Finding: sr's ugly numbers are REAL (selector picks HRRR, so historical L5_NBM stamps never touched Prod). L5_NBM kill was pipeline hygiene, not user-facing damage. **Solar is real forecasting difficulty, not stale-layer contamination** — Joe's reframe.
- HRRR-side counterfactual deferred (layer slots are field-dependent; needs per-field disable logic).

**v0.6.496 — closed 4 overdue watches + h/dp/sr Status column narrative:**
- Closed CLEAN (14d elapsed, no triggers): pr L2 regime-gated, chp diurnal gate, walkforward L3/L4, C1h re-curate.
- Updated per-field pipeline architecture Status columns for h, dp, sr with today's L2_NBM audit + delta-skip context + sr counterfactual verification.

**v0.6.497 — L2_NBM prose reflects audit reality:**
- Applicability block + parity callout rewritten to describe 6-field transfer (not 9), cite audit findings, retire "cheap and captures most of the value" (audit doesn't support it), flag "evidence-graded per-cell skip table" as the plausible longer-term architecture.
- Retired dated "clp streak walker · day 3/7 · earliest flip 08-16" in 3 spots.

**v0.6.498 — NATIVE NBM L2 for additive-bias family (t/h/dp):**
- Joe pushed: if goal is parity, we need to build it now, not stopgap. Right.
- `_L2_NBM_NATIVE = {t, h, dp}` initial. `_prod_error_current_config` unchanged (only skips NBM disabled).
- New `_nbm_l2_native_arrays` precompute in `forecast_snapshot.stamp()`: `bias_nbm_t = weighted_bias + (raw_hrrr_t[0] − raw_nbm_t[0])`; `l2_nbm_t[i] = raw_nbm_t[i] + K * bias_nbm_t * t_decay(i)`. Same K + tau HRRR uses.
- dp derived Magnus(l2_nbm_t, l2_nbm_h) at each lead.
- `_build_nbm_raw_array` helper walks per-lead UTC keys against nbm_by_valid_utc.
- Delta transfer path retained for ws/wg/wd/cc/ch (phase 2).

**v0.6.499 — NATIVE NBM L2 for wind + cloud families (parity closed):**
- `_L2_NBM_NATIVE = {t, h, dp, ws, wg, wd, cc, ch}` — all 8 NBM-scope fields.
- Wind family: mirrors wind_blend.py's linear time-decay of current observed into [0, BLEND_HOURS) on NBM raw arrays. wd uses circular unit-vector blend with WIND_DIR_MIN_SPEED calm-floor guard.
- Cloud family: mirrors cloud_obs_blend.py's hourly[0] K·(obs_mean − raw), reusing HRRR's Kalman gain + obs means from cloud_l2_meta.
- sr stays identity — HRRR has no L2 for sr, no station network for solar, nothing to mirror.
- **Delta transfer approximation fully retired for NBM-scope fields.** _L2_NBM_DELTA_SKIP kept as alias for {sr} only.

**v0.6.500 — skip-table first-real-pass:**
- 9 new evidence-graded cells added to `skip_table_nbm_curated.json` (7 wg + 2 ch across nw_flow/pre_frontal/se_flow bands, filtered to fields in L3_NBM_FIELDS). Total l3_nbm cells: 8 → 17.
- cc excluded despite big lift numbers because Ccd overwrite makes cc L3_NBM no-op for user output. Joe caught this.
- Counterfactual rescore confirmed: wg 6-11h +4.08%, wg 12-23h +2.53%, ch 0-5h +1.98%; 1 selector flip (wd 12-23h HRRR → NBM after `analysis/l1_selector_fit.py` re-fit).
- Selector picks: 9 → 10 (wd 12-23h added). Router-scope ship-gate NBM lift +53.5% n=73,023.

## Product state at end of session

- **Total Lift ≈ 0** (median), **Pipeline Lift > 0**, **Selector Skill > 0** — the "almost absurdly clean" state Joe called out.
- Solar (sr) is the remaining real forecasting problem — not NBM pipeline debt (proven via counterfactual).
- Halves agreement 50%, 6 LOW-confidence fields — a noisy near-parity week; today's readings don't overinterpret.

## Categorical framing (Joe taught me this today)

Parity = ARCHITECTURE only. NOT data state, ENABLED flags, or pair-log depth.
- **Parity gap:** processor slot doesn't exist. As of v0.6.499, none.
- **Data project:** table under-curated. e.g. skip_table_nbm went from 8 → 17 cells today.
- **Runtime decision:** ENABLED flag. e.g. L6_NBM = False pending waterfront investigation.
- **Calendar:** time fills it. e.g. deeper NBM layers <10d live coverage.

Don't roll these into a single "parity" list.

## Follow-ups for next session

**Wait-on-calendar:**
- L2_NBM audit tomorrow — 1/30 rolling window will be native L2; effect not visible yet.
- Native L2 fully occupies audit window ~09-25.
- Skip cells v0.6.500 post-ship 14d watch through 09-09.
- wg L3 8-cell skip (v0.6.475) post-ship 14d watch through 09-08.
- cc.l4_nbm HOT day-2 sentry check tomorrow.

**Available now if desired:**
- **L6_NBM waterfront investigation** — native L2 unblocks it. Could fit L6_NBM against fresh error_l2_nbm residuals; enable if lift.
- **cc_combine_gate walker** (seeded 08-17) — Ccd formula tuning. Not user-critical since cc is derived.
- **HRRR-side current-config counterfactual** — per-field disable logic. Real work; only useful once a HRRR layer gets killed/demoted.

**Small cleanups:**
- `_L2_NBM_DELTA_SKIP` alias in forecast_snapshot.py now just {sr}; could be renamed or retired.
- `nbm_backstamp.py` still uses delta approach — appropriate for legacy historical rows, but worth a docstring note.

**Discovered gap in tooling:**
- Historical backstamp for native L2 not feasible — pair log doesn't carry hyperlocal state per historical run. Native L2 fully saturates the rolling window via calendar (~30d).
