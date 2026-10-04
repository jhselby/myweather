---
name: 08-17-session
description: "2026-08-17 session log. Four commits (v0.6.425-428), 20-file 'error field is L2' analysis sweep, six same-day workstream closures (5 from same 'recent obs predicts near future' failure mode). Meta-finding: honest run-time-keyed walkforward is the only test that survived — every leaky Stage 0 HIT was retracted same-day. No user-visible shipped wins; all progress is subtractive (know what NOT to do)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 32832742-5efb-4b02-a23b-3cd645f9da4d
  modified: 2026-08-17T20:57:19.735Z
---

# 2026-08-17 session log

## What actually shipped (4 commits)

- **v0.6.425 — Analysis truth-telling sweep.** `analysis/_prod.py` helper + 20 analysis scripts converted from L2-residual (top-level `error` field) to real production residual (`error_{applied_layer}`). Rooted out silent lies across the digest. `anomaly_detector` now reports cm WATCH +32.6% (was CLEAN −3.9%); cc drops to CLEAN because Ccd derivation catches it. See [[feedback_top_level_forecast_is_l2]].
- **v0.6.426 — Lc EMA/Kalman fallback CLOSED MISS same-day.** Stage 0 leakage: obs-time-keyed shift lookup peeked at obs from up to 24h more recent than issue-time. Honest run-time-keyed sim hurts cl at every N, validates on cc/cm/ch. See [[project_lc_ema_kalman_fallback]].
- **v0.6.427 — cl h-predictor router CLOSED MISS same-day.** Stage 0 real (h_fc disagreement cells 1.59× MAE) but Stage 1 halves catastrophically failed (Half A −35% / Half B +34%). See [[project_cl_h_predictor]].
- **v0.6.428 — Lc gate rule direct-MAE CLOSED MISS same-day.** Investigating cm walker churn; proposed rule leaked (decision + scoring same holdout window). Honest walk shows zero different decisions. cm walker churn is real regime volatility, not a gate bug. See [[project_lc_gate_rule_direct_mae]].

## Six same-day closures (not just the four committed)

Also closed inline without new scripts:
- **Regime-conditional Lc for cm** — pre-existing flat verdict (reg_vs_pool −0.21%) confirmed on fresh walkforward. Bin membership already does most of the regime-separation work. See [[project_lc_regime_conditional]].
- **sr 8a/8b obs-recent override** (Backlog #8) — 8a fresh run flipped from 08-11 near-hit to clear miss (test pool −5.79%, fired subset −43%). 8a script also has run-time keying leakage (obs_prev = vt−1h regardless of lead; for lead=6, that's 5h future). 8b honest test hurts even more at trigger 100 (−47%). Both dead. See [[project_hypothesis_backlog]] item 8.

## The meta-finding

**Every "recent obs predicts near future" architecture failed today, six for six:**
1. Lc EMA/Kalman (leakage-inflated Stage 0)
2. cl h-predictor routing (halves-unstable)
3. Lc gate rule direct-MAE (leakage-inflated Stage 0)
4. sr 8a obs-recent override (signal decay + leakage)
5. sr 8b cloud-disagreement (same premise as 8a)
6. Lc rolling-window sweep for cl (all N hurt at all bands with honest keying)

**Physical read:** cl / cm / sr are all fast-moving regime-driven fields where 3-6h obs history doesn't project 3-6h forward during regime shifts. The wet-regime week (se_flow / pre_frontal / frontal dominance) exposed this at every architecture level.

**Design implication:** future ideas on these fields should avoid the "recent-history persists" premise. Try instead:
- Structural features (regime classification without history dependence)
- Longer horizons (weekly / seasonal patterns)
- Regime-change detection (turn corrections OFF during transitions)

## The leakage class

Three distinct instances same-session, all the same shape:
1. **EMA per-row updates on repeated obs** — naïve per-row EMA collapses to persistence when there are 48 rows per obs_time.
2. **Obs-time vs run-time keying** — using obs available at obs_time (or vt−1h regardless of lead) when in production we'd only have obs available at run_time.
3. **Same window for decision + scoring** — computing "does live shift help on the last 3d" and then scoring the gate on the same 3d.

**Design rule going forward:** for any future pair-log-based hypothesis, split decision-data from scoring-data BEFORE writing the first line of code, not after the first HIT. Consider extracting `analysis/_walkforward_honest.py` as a shared harness if a fourth instance shows up.

## Walker audit outcome

Audited `walkforward_lc_regime.py` and `walkforward_l3l4_validator.py` for the same leakage classes we caught today.

- **walkforward_l3l4_validator.py: CLEAN.** Compares historical `forecast_l1/l2/l3/l4` values (what production shipped at issue time) vs obs. No fit, no counterfactual. L3=[ch, cm, wg] / L4=[cc, ch] SHIP decisions are trustworthy.
- **walkforward_lc_regime.py: mild boundary leakage.** For test rows near cutoff with long leads, training table includes obs from AFTER those rows were issued. Magnitude ~47h × ~16% of test rows. Effect ~1-3pp overstatement on reg_vs_raw and reg_vs_pool. Doesn't change the SHIP decision. Not urgent.
- **simulate_windows.py: CLEAN.**

## What did NOT clear today (from the debug page + memory)

Yesterday's expectations that didn't happen:
- **cm's recent-bias gate walker** was expected to clear its 7-day per-field streak today (per pipeline-to-good item 3, 08-14 write-up). Did NOT clear — cm streak 0/7, promoted only 4 of 7 window-days. Set off the whole afternoon investigation.
- **h regime bias watch 08-16** expected h to revert to CLEAN once the ridge broke. Still WATCH +17.4% ΔMAE. Ridge hasn't broken.

## Open items closing this week — CHECK TOMORROW

1. **dpbp 14-day post-flip watch closes 08-18 (tomorrow).** dp_bias_persistence gate shipped 08-04 v0.6.391. Nothing flagged today; likely clean-close but read the digest.
2. **Lsb 14-day post-flip closes 08-19.** sr sea_breeze cc<25 override shipped 08-05 v0.6.394. Same status.
3. **walkforward_lc_regime_ship_stability** — day 5/7 with earliest READY 08-20 (Wednesday). If it clears, Stage 3 wire for regime-conditional Lc is unblocked.

## Still-running walkers (no action)

- Lsr recent-bias gate + chp cell gate — earliest per-cell flip 08-23
- clp Stage 3 flip gate — walker FAIL day 3/7, no flip in sight
- ch chp regression watch — 14-day watch through 08-27, day 1/7 vs_l6 evidence today (6 cells losing, worst se_flow/6-11 +68%)

## What tomorrow's digest will show that today's didn't

The 20-script sweep from v0.6.425 lands automatically in tomorrow's digest run. Expect:
- `anomaly_detector` verdict line changes from `watch: cc, dp, h` to `watch: cm, dp, h` (cc drops out, cm enters)
- `h_persistence_skill` numbers unchanged (already reconstructed prod correctly)
- `mae_over_time` unchanged (already had `prod_real` path)
- Various C1 hypothesis Stage 0/1 scripts now report against real prod residual (probably marginal number changes; verdicts unlikely to flip)

## Files added / modified this session

**Repo (committed):**
- `analysis/_prod.py` (new)
- 20 analysis scripts modified for `_prod` import + call swap
- `analysis/h_lc_ema_stage0.py` (new, kept with retraction header)
- `analysis/h_lc_ema_stage1_baseline.py` (new)
- `analysis/h_cl_h_predictor_stage0.py` (new)
- `analysis/h_cl_h_predictor_stage1.py` (new)
- `analysis/h_lc_gate_rule_stage0.py` (new, kept with retraction header)
- `analysis/h_lc_gate_rule_stage1.py` (new, kept with retraction header)
- `index.html` / `sw.js` / `version.json` / `docs/CHANGELOG.md` — version bumps

**Memory (this store):**
- `project_cm_lc_wet_regime_watch.md` (new)
- `project_lc_ema_kalman_fallback.md` (new)
- `project_cl_h_predictor.md` (new)
- `project_lc_gate_rule_direct_mae.md` (new)
- `feedback_top_level_forecast_is_l2.md` (updated with sweep record)
- `feedback_pair_log_error_field.md` (marked SUPERSEDED)
- `project_ch_chp_regression_watch_08_13.md` (updated with 08-17 day-1 evidence)
- `project_plan_pipeline_to_good.md` (updated with EMA + h-predictor closures)
- `project_hypothesis_backlog.md` (updated with 8a/8b closures)
- `MEMORY.md` (index refreshed)

## No collector deploy

All work is analysis-side. Collector didn't change. Next digest run (tomorrow 07:21) auto-picks the new scripts.

## What to say if Joe asks "what happened yesterday"

Big honest day. Sweep the digest so it stops lying; try three cl rescue architectures and close all three; try one cm gate-rule improvement and close it; try two sr obs-override variants and close them. No shipped user-visible win. Six workstreams closed with real answers. The `_prod.py` sweep is the durable artifact that makes tomorrow's digest trustworthy.

## Related

- [[project_plan_pipeline_to_good]] — item 3 fallback branches all closed today
- [[project_cm_lc_wet_regime_watch]] — opened this session
- [[feedback_check_contamination_before_acting]] — the class of failure this session illustrates
- [[feedback_hypothesis_promotion_pipeline]] — the discipline that caught six MISS verdicts
- [[project_ch_chp_regression_watch_08_13]] — day 1/7 of vs_l6 gate today
- Recent session logs: [[project_08_10_session]] · [[project_08_10_confidence_axes_sweep]]
