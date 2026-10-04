---
name: project-09-12-session
description: "2026-09-12 (Sat) — 9 ships. Morning: pr L2 unwire (3-tool). Escalation clause from 09-11 vindicated (h -522% → +7.2%). Afternoon: digest pruning (13 retired, 4 stubs added), 7 hypothesis-test scripts (5 PROMOTE, 1 MARGINAL, 1 HOLD). inter_model_spread cleared Stage 0 → Stage 1 orthogonality → Stage 2 preview (33 SHIP cells, 09-19 wire gate armed). 3-way selector fitter (6 NWS-wire cells, 5 dp on nw_flow/pre_frontal/sw_flow up to +29% lift halves-stable). First new C1-axis candidate to reach Stage 2 since cross_run_spread in June."
metadata:
  node_type: memory
  type: project
  originSessionId: session_016sc88nJz5HLV5o5CqPsjkA
  modified: 2026-09-12T15:06:40.215Z
---

# 09-12 Sat — pr L2 unwire, escalation clause vindicated, holds otherwise

## First-read: escalation clause confirmation

Session opened with the 09-11 memory pointing at h/ws/wg/sr/dp 24h VC as the escalation-clause verdict. Result:

- **h**: total lift +7.2% (was -522% yesterday) — massive recovery
- **ws**: +12.5% (sel_n +24.8% ← escalated cell earning)
- **sr**: +21.4% (corr saving it despite sel_h -39.8%)
- **wg**: -7.8% (still red)
- **dp**: -18.0% (still red — see below)

7d value-add mean +10.98% (6g/3a/0r). 24h still -67% aggregate but the specific fields we targeted (h, ws) recovered. Escalation clause working as designed.

Two of yesterday's wires flipped OUT of the walker today:
- `ws/calm/0-5` (NBM-wire from AM shipped 09-11)
- `ws/nw_flow/12-23` (NBM-wire — one of the original two AM ships) — flipped inside window per today's walker. Walker correctly withdrew.

HRRR-wire escalation cells `h/calm/24-47` + `ws/sea_breeze/24-47` both holding.

## v0.6.590 — pr L2 gate: unwire nw_flow/6-11h

**Three-tool agreement** that the shipped `pr/nw_flow/6-11h` cell was losing:
1. `pr_l2_regime_lead_retro`: pooled Δ **−13.6%** over 1,447 pairs since 08-13, both chronological halves negative (A −8.5% n=658 / B −17.7% n=789).
2. Layer-shape sentry: `pr/production@6-11h +10.6% vs raw` (production making error worse than raw).
3. Yesterday's Notable Calls: `pr 6-11h −8.7% n=942`.

The 08-10 Stage 1 both-halves that justified the ship (A +10.3% / B +13.1%) has inverted. Persistent regression across a month of live data, not noise.

**Fix:** removed `("nw_flow", "6-11")` from `_PR_L2_FIRE_CELLS` in `weather_collector/processors/corrected_hourly.py:38`. `nw_flow/0-5h` retained — retro confirms HEALTHY (pooled +6.4%, halves +11.7%/+1.9%). Shadow-wire stays unconditional.

Collector deployed 10:19 UTC (rev `myweather-collector-00563-few`, ACTIVE). Frontend pushed `main` at `e3b0ce6`.

**Watch:** pair-log MAE for pr short-lead nw_flow rows returns to raw once new obs stamp `applied_layer=l1` in the 6-11h band. Layer-shape sentry for pr 6-11h should clear over next few days.

## Holds (with reason)

Four candidates reviewed and held after diagnostic — none shipped, each for a specific reason:

**1. dp -18% corr regression.** Standing rule per [[project_dp_is_derived_no_dp_work.md]]: dp = Magnus(t, h), so dp regressions route to t/h investigations first. Both t (+14.4%) and h (+7.2%) are winning at production today. The dp regression is either small-window artifact (like cm -654% today which flagged CLEAN on anomaly detector) or dpbp misfiring on today's regime mix. Not opening a dp workstream.

**2. ch -17.7% total lift / chp gate vs L6.** `h_ch_persistence_blend_stage2_vs_l6` shows 7 live chp cells losing to L6 baseline (worst se_flow/6-11 Δ+29.91%). But the escalation playbook is explicit: **7 daily reads / 2-tool / per-cell / no-ENT before flipping — today is day 1**. Playbook adherence over premature action. Cells for the watch: ne_flow/6-11, nw_flow/0-5 & 6-11, pre_frontal/0-5 & 6-11, se_flow/6-11 & 12-23.

**3. wg.l3_nbm sentry HOT** (+5.3% → -4.6%). Single-tool signal. Walkforward disagrees (aggregate wg.l3_nbm still EARN +3.1% over 30d). All 3 wg skip-ADD proposals came back **STALE** on today's 50d two-window audit (regime-transient — 14d hurts, 50d helps). This is exactly the class of signal the ADD two-window gate shipped yesterday (v0.6.584) exists to catch. No action.

**4. walkforward `wdp_nbm DROP wd` proposal.** On n=107 pairs (THIN). Below any ship floor. `l3_nbm ADD cc,wd` — cc was killed 09-10 (walkforward hasn't caught up); wd already resolved via today's ADD two-window audit (1 CONFIRMED shipped yesterday, 2 FRESH holds).

## Standing signals not affecting today's ship queue

- `cm -654%` per_field_scoring — noise artifact from small-variance window (cm raw MAE 0.32, tiny denominator). Anomaly detector CLEAN. Persistence-skill shows cm Prod adding +0.29 skill.
- Walkforward wants to drop cm from L3_FIELDS: GATED 4/7 days, clears 09-15.
- ADDED_LAYERS entries for sr auto-clear 09-14 when sustained window fully post-dates the 09-04 add.
- KILLED_LAYERS 09-05 entries (ch/chp_nbm, h/l3_nbm) prunable 09-15.

## Afternoon session — new-hypothesis pipeline

Started with the strategic question "will the digest ever produce another correction layer" — I answered pessimistically. Joe pushed back: "come up with new shit to try." What followed:

**v0.6.592** — digest pruning. Retired 13 dead-weight scripts (all CLOSED-MISS/retired-mechanism/perpetual-HOLD firing daily) via `.skip.py` rename. Added 4 replacement scripts: `h_pre_front_orthogonality.py` full rewrite (matched-regime baseline, mirror of working hsf structure — first-run 4 ORTHOGONAL cells wg/cm long-lead, THIN population until autumn) + 3 Stage 0 scaffolds (`h_cloud_saturation_bias_stage0`, `h_regime_transition_correction_off_stage0`, `h_sr_regime_conditional_lsr_stage0`). Digest 183 → 170 scripts.

**v0.6.593** — 4 new Stage 0 hypothesis-tests, real analyses:
- `h_inter_model_spread_stage0.py` → **PROMOTE 35/36 cells.** |forecast_l1 − forecast_raw_nbm| per row. Q4/Q1 MAE ratios 1.4×–5× halves-stable every field with NBM data. Caveat: signal partly self-referential — legitimate for C1 confidence-widening, needs orthogonality proof before biasing.
- `h_prior_day_error_c1_stage0.py` → **PROMOTE 14/40.** Strong 0-5h short-lead signal across t/h/ws/wg/cc/dp; ch across all bands.
- `h_diurnal_l2_tau_stage0.py` → **MARGINAL.** sr 4.69pp + wg 3.37pp HOD spread — mid-day convection reduces predictability. Other 8 fields FLAT.
- `h_buoy_sst_gradient_stage0.py` → SCAFFOLDING. Buoy 44013 SST fetched but not per-row-logged.

**v0.6.594** — Stage 1 orthogonality on the two PROMOTEs vs 3 per-row-available C1 axes (C1a transition, cluster_spread, pt_mag).
- **`inter_model_spread` → STAGE 1 PROMOTE.** C1a 33/36 ORTHOGONAL (0 REDUNDANT), cluster 36/36 (0 REDUNDANT), pt_mag 34/36 (1 REDUNDANT). Genuinely independent signal.
- `prior_day_err` → HOLD. Mixed 19/13/8 across axes. Short-lead cells stay orthogonal (matching Stage 0 pattern) but mid/long lead contribute REDUNDANT. Narrow-ship candidate at 0-5h only.

**v0.6.595** — Stage 2 preview for inter_model_spread. `h_inter_model_spread_c1_stage2.py` — 14d test window, halves-stable check, MIN_PREMIUM_SHIP=30%, MIN_N_SHIP=500. **STAGE 2 PROMOTE — 33 SHIP cells** across every non-cl field. Premiums 40-500% for t/h/ws/wg/wd/cc/ch/dp. sr numbers pathological (60k-90k% because Q1 = near-zero-MAE night rows — needs floor filter at wire time). 7-day stability gate armed → **earliest wire 2026-09-19**. First new C1-axis candidate to reach Stage 2 since cross_run_spread in June.

**v0.6.596** — 3 more Stage 0s exploiting under-used pair-log features (found `forecast_nws`, `error_nws`, `selector_source` per row):
- `h_three_way_spread_stage0.py` (HRRR/NBM/NWS σ) → PROMOTE 15/16. Not superior to 2-way (reduced coverage). Keep 2-way as wire candidate.
- `h_nws_source_check_stage0.py` → **PROMOTE 7 halves-stable NWS-optimal cells.** dp/nw_flow 3 leads (25-30% better), dp/pre_frontal, dp/calm, ws/sw_flow 2 leads. Concrete routing miss.
- `h_state_fc_obs_disagreement_stage0.py` → PROMOTE both cloud_delta (12 cells) + solar_delta (13 cells).

**v0.6.597** — `analysis/l1_selector_fit_3way.py`. Standalone 3-way fitter mirroring by-regime fitter's 30d window + halves-stability. NWS covers 5 fields (t/wd/ws/dp 100%, pp 76%). **First-run 6 NWS-wire cells** clear halves-stable + lift ≥ 3%:
- **dp/nw_flow/12-23: +29.3%** (h1/h2 13.4/33.7, n=1,721) — escalation-clause eligible
- dp/nw_flow/0-5: +26.1% (8.7/31.0, n=1,229)
- dp/pre_frontal/12-23: +24.8% (27.5/18.3, n=1,044)
- dp/nw_flow/24-47: +13.6%, dp/sw_flow/24-47: +9.8%
- t/frontal/6-11: +9.7% (thin n=84, masked)
Runtime + walker NOT touched — analysis-only. Follow-on wire path documented.

## Follow-on for next session (top priority)

**Extend L1 selector to 3-way NWS routing.** Three files change:
1. `analysis/l1_selector_fit_by_regime_walker.py` — track 3rd direction (NWS-wire) alongside NBM-wire + HRRR-wire. Same 3-day gate + escalation clause as v0.6.586-588. Mutual exclusivity by construction.
2. `weather_collector/processors/l1_selector.py` — extend `pick_source()` to consult `cleared_for_wire_nws` and route NWS when the walker clears a cell.
3. Debug-page Upcoming grid row for 09-19 first-read.

**dp/nw_flow/12-23 qualifies for escalation-clause immediate wire** on day 1 by the exact criteria shipped 09-11 v0.6.588 (halves-stable + |lift|≥20% + n≥500). Expected lift: current best-of-HRRR-NBM MAE ~1.93 → NWS MAE ~1.36, Δ 0.57°F × 57 rows/day × 30 days = 975°F-days of dp error saved per month on that one cell.

## Clock-watches carried forward

- **09-13 (Sun) FIRST-READ:**
  (a) pr pair-log MAE at `nw_flow/6-11h` should return to raw as new obs stamp `applied_layer=l1` in the 6-11h band. Layer-shape sentry for pr 6-11h should trend clean.
  (b) 3-way fitter day 2 — verify dp/nw_flow SHIP cells stable across two reads.
  (c) day 2/7 of chp L6-baseline demote gate.
  (d) inter_model_spread Stage 2 day 2/7 of stability gate.
- **09-14 (Sun)** — first HRRR-wire GATED read (7 walker candidates). sr ADDED_LAYERS prunable.
- **09-15 (Mon)** — L3 DROP cm walkforward streak; KILLED_LAYERS 09-05 entries prunable.
- **09-19 (Fri) KEY DATE** — inter_model_spread Stage 2 7-day gate clears → wire as C1 axis_6 in `c1_confidence_calibration_v2.py`. Also pr L2 gate stability re-read.
- **7d watch on today's ship** — pr pair-log MAE at `nw_flow/6-11h`.
- **Rolling** — 3-way fitter dp cells stability across daily runs.

## Lessons

- **Standing rules first.** The dp -18% would have been tempting to open a workstream on. The derived-field rule ([[project_dp_is_derived_no_dp_work.md]]) settled it in one memory read. No spiral, no false start.
- **Playbook discipline over co-owner urgency.** The chp L6-baseline verdict is loud (7 cells, worst +29.91%), and yesterday's memory framed pillar 1 (scoring) revealing pillar 2 (fix) as the win pattern. Playbook still says 7 daily reads. Waiting was the right call — a premature demote-then-re-add is the same class as the ws/nw_flow/12-23 flip today.
- **Two-window audit paying dividends.** wg.l3_nbm sentry HOT + 3 walkforward skip proposals would have shipped 3 skip cells under the old 14d-only gate. Two-window rescored all three STALE (50d shows helping). System doing its job.
- **Escalation-clause bet paid off.** h VC recovery from -522% → +7.2% total lift on a 20h horizon is validation that halves-stable × large × plenty-of-n cells shouldn't wait 3 days.

## Related

- [[project_09_11_session]] — the walker/escalation session that set up today's read.
- [[project_pr_l2_gate_ordering_fix]] — original context for pr L2 gate, superseded by today's unwire on nw_flow/6-11h.
- [[project_chp_midlead_regression_watch]] — the escalation playbook governing the 7 chp cells.
- [[project_dp_is_derived_no_dp_work]] — the rule that closed the dp diagnostic in one read.
- [[feedback_metric_independence_paradigm]] — pillar 1 = scoring, pillar 2 = model work; today's ship followed the pattern.
