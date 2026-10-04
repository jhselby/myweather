---
name: project-todo
description: "Active/pending work. **Refreshed 2026-08-31 evening.** Live version v0.6.533. Today's session totals: 7 ships + 2 collector deploys (v0.6.527–533). Marquee: (1) v0.6.527 fixed 6 residual-persistence wrapper FAILs (missing sys.path.insert after 08-30 harness extraction). (2) v0.6.528 Stage 1 harness picks halves-stable-best not raw-max — see [[feedback_grid_select_halves_stable]]. (3) v0.6.529 Stage 2 → Stage 3 promotion walker built + wired to daily digest — closes manual-review gap. (4) v0.6.530 h_residual_persistence.py Stage 3 processor pre-staged + wired collector-side ENABLED=False + **deploy #1** verified live. (5) v0.6.532 Stage 3 processor harness extracted (three ~230-line clones → 290-line shared module + 3 × ~50-line wrappers, 245 lines cut, byte-hash 6b6c5293acc6126b matched pre/post) + **deploy #2** verified live on ne_flow tick. (6) v0.6.533 evening sweep: L1 selector refit (`l1_selector.py`) now ships dp/wg/wd/cc to NBM at ≥6h — this SUPERSEDED my same-session 'NWS-dp PROMOTE +44.6%' memo (was measuring vs selector-routed prod, magnitude inflated by dp-derived-exclusion arc). REAL residual finding: selector fits band-level only; regime × band cells where NBM wins under a pooled-HRRR band are MASKED (ws 8 cells, t 1 cell). See [[project_nws_dp_promote_08_31]] and [[project_08_31_session]]."
metadata:
  node_type: memory
  type: project
  modified: 2026-09-05T01:07:56.551Z
  originSessionId: ad1280d2-1737-4f15-91dc-0a8e9834b066
---

## P1 — Active watches (drift risk this week)

| Item | Day | Through | Trigger |
|------|-----|---------|---------|
| **h_residual_persistence Stage 3 shadow-telemeter** (ENABLED=False, v0.6.530, deploy #1 verified live) | 0/N | ship-day flip earliest ~09-06 | Walker clearance of promotion cells + shadow telemetry clean vs L6 baseline |
| **Stage 3 shared harness** (`_residual_persistence.py`, v0.6.532, deploy #2 verified live on ne_flow tick) | 0/7 | 09-07 | Any of wg / dp / h residual-persistence telemetry diverging from pre-refactor byte-hash behavior; fires 0 / skips 47 confirmed on ne_flow first tick |
| **t/6-11h τ-suspect** (top-alert day 2 → day 3, no ship) | 3/N | daily until stable | Absolute Δ has slipped 0.06°F (day 2) → 0.075°F/day (day 3, ~noise band). L2 flipped +5% helping → −7% hurting week-over-week. Watch day 4 tomorrow 09-01. Authoritative decay_tau_tuning (457K rows) says τ=42 optimal — no code change unless day 4+5 keep drifting. See [[project_t_6_11h_tau_watch_08_31]]. |
| **v0.6.525 telemetry bugfixes verified live** (`clamped_out_by_band` + `record_firing`) | verified | — | 16920 skips (47 leads × 360 regime-ticks) across 1009 ticks / 7 days on wg + dp + now h processors, all through shared harness |

## P2 — Next actionable ships

1. **Selector per (field, regime, band) extension — RE-CHECK 09-07.** Diagnostic script shipped 08-31 evening as `analysis/l1_selector_fit_by_regime.py` (writes `l1_selector_by_regime_report.json`). 30d run flagged 8 masked cells (dominated by ws-calm short/mid/long-lead +33–41% halves-stable). 7d run flagged **only 1** (ch/nw_flow/6-11h, borderline halves). The 30d window is 96% pre-refit — masked cells are very likely an artifact of the same pre-refit baseline that superseded [[project_nws_dp_promote_08_31]]. Wait for clean post-refit 30d window: re-run `python3 -m analysis.l1_selector_fit_by_regime` on/after **09-07**. If ws-calm (or any other) cells still show halves-stable ≥ +10% on n ≥ 200, extend runtime `l1_selector.py` to key on (field, regime, band). Otherwise close as no-residual.
2. **h_residual_persistence ENABLED=True flip** — earliest 09-06 pending walker cell clearance. Currently shadow-telemetering. Deploy #1 verified 08-31; watch daily digest for walker to promote cells. Same shape as wg's flip.
3. **sr Stage 2 08-31 re-read follow-up** — HOLD on pooled Stage 2, but hours 17-18 surfaced as a narrow ship candidate. See [[project_sr_stage2_08_31_read]]. Needs Stage 2 halves re-run scoped to hours 17-18 only.

## P3 — Analysis / candidates (open, no ship-date)

- **Scoreboard short-window (6h or 12h)** — added 09-04. The current 24h/7d windows are dominated by pair-log lag for days after any override/selector-fit ship (a fresh override touches only ~8-10% of the 24h window on the first day; full 24h rotation takes ~48h; full 7d takes 7d). A 6h or 12h window on scoreboard_v2 would surface post-ship quality immediately. Estimated ~30 min build. Also add ~24h post-override sample size to the debug page as a "confidence weight" for the short window so we don't overreact to thin samples.
- **cc combine walker** — [[project_cc_combine_walker]] open work.
- **cm Lc wet-regime watch** — [[project_cm_lc_wet_regime_watch]].
- **Lc regime-conditional** — [[project_lc_regime_conditional]] + [[project_lc_regime_stage1_pool_prereq]] pool-prereq.
- **Lc cl un-skip investigation** — [[project_lc_cl_unskip_investigation]].
- **clp Stage 3 flip** — [[project_cl_persistence_investigation]].
- **pr L2 gate ordering fix** — [[project_pr_l2_gate_ordering_fix]] (scheduled close 08-27; verify status).
- **pp Brier reliability** — [[project_pp_brier_reliability]]. pp recalibration [[project_pp_recalibration_session]] dormant.
- **ppbp workstream Stage 1** — [[project_ppbp_workstream]] queued.
- **h regime bias watch** — [[project_h_regime_bias_watch_08_16]] (scheduled close 08-23; verify status).
- **dp residual persistence short-lead** — [[project_dp_residual_persistence]] permanently ENABLED=False per today's re-attribution (dp is derived; signal re-routed to h upstream via Magnus). Keep for reference only.
- **wg residual persistence** — [[project_wg_residual_persistence]] live via shared harness.
- **wg L3 skip-table** — [[project_wg_l3_skip_table]].
- **wg L2 windblend cell concern** — [[project_wg_l2_windblend_cell_concern]].
- **sr unit mismatch** — [[project_sr_unit_mismatch]].
- **NBM skip-proposals review** — [[project_nbm_skip_proposals_review]] scheduled 09-09 (44 per-regime SKIP proposals; wait for sustained-7d post-backstamp before curating).

## P4 — Refactors / deferred

- **Confidence axes:** cross-run spread c1 LIVE [[project_cross_run_spread_c1_axis]]; recent-|err|-streak c1 parked [[project_recent_err_streak_c1_axis]].
- **Cross-cutting infra:** metric provenance [[project_metric_provenance_v0391]] · raw-difficulty index [[project_raw_difficulty_index]] · antecedent pattern [[project_antecedent_pattern_generalization]] · collector memory leak hunt [[project_collector_memory_leak_hunt]] · hypothesis backlog [[project_hypothesis_backlog]] · chooser fit diagnostics [[project_chooser_fit_diagnostics]].
- **Migrate chp/clp/wdp onto `persistence_gate_base.py`** — helper shipped v0.6.382q; three concrete specialists still on hand-rolled code. Follow-up commit once their post-ship watches close (all long since closed — this is genuinely stale, do or drop).
- **Extend asymmetric SKIP infra to Lsr** — waiting on unit-mismatch resolution per [[project_sr_unit_mismatch]].
- **pp τ=28 validation gap** — extend `pp_brier_reliability.py` to sweep τ values (7/14/28/42) and pick min-Brier.
- **pp calibration under-forecasts wet outcomes** — bin-weighted probability lift table Stage 1 candidate (predicted 35% → observed 62% at 30-40% bin).

## Product-idea backlog (not correction-stack)

- **Wyman Cove Swim Index (WCSI)** — swim-safety score combining recent rainfall runoff, tidal flushing, outfall observations, Salem-area beach closures, wind direction. Scoring proposal + open design questions TBD. No date; pull in on a low-load day.

## P5 — Settled / do not re-open

See [[MEMORY]] "Subsumed by v0.6.432 router" and "Settled / do-not-reopen" sections. Highlights: t L2 ceiling · MLC · cc-sat correction · Lt · CC-sat · L6 cooling · ws L3 regression · ws recovery 08-04 · chp cell→dynamic (CLOSED CLEAN 08-25) · Lsr recent-bias gate (CLOSED CLEAN 08-25) · sr Lsb (CLOSED CLEAN 08-19) · dpbp (CLOSED CLEAN 08-18).

---

## Recent ship history

For per-day narratives see the session logs indexed in MEMORY.md. Today's is [[project_08_31_session]]. Prior big days: [[project_08_30_session]] · [[project_08_29_session]] · [[project_08_28_session]] · [[project_08_27_session]] · [[project_08_26_session]] · [[project_08_25_session]] / [[project_08_25_evening_session]].
