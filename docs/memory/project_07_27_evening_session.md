---
name: 07-27-evening-session
description: "2026-07-27 evening extension after PM commit 96d049d. Five commits, v0.6.382q → v0.6.382u. Two marquee findings: (1) first shippable pp correction ever found — frontal × 6-11h Platt with fixed b=0.6, Stage 1 SHIP (-28.56%/-18.73% Brier lift, |Δa|=0.20). (2) chp Stage 2 was measured against forecast_l4 (pre-Lc baseline); post-Lc-flip the honest baseline is forecast_l6 — rebuild shows honest SHIP set is 5 cells not 28. 6 clear-regression cells surgically demoted v0.6.382t. Also: persistence_gate_base helper extracted; pirate_l1_log per-tick logging shipped (14-day clock for 3-source pp blend); h_pp_source_blend Stage 0 HOLD (HRRR+GFS near-collinear); clp gate extended 07-31 → 08-03."
metadata:
  node_type: memory
  type: project
  originSessionId: 91839d01-66b3-4e8e-b34e-1d31f626be5d
  modified: 2026-07-28T10:36:11.142Z
---

# 07-27 evening — v0.6.382q → v0.6.382u (5 commits)

Followed on from PM session's commit 96d049d (v0.6.382p, HANDOFF written). Joe: "keep working" → 3 planned tasks (A/B/C) plus sweep → then "keep going" → 2 more (chp ESCALATE + frontal pp Stage 1) → then chp emergency demote → then debug page sweep.

## Commits

| Ver | Commit | Change |
|---|---|---|
| q | 8e99fd6 | clp 7-day gate EXTENDED 07-31 → 08-03 (post shadow-write fix needs 7 full daily reads) + `persistence_gate_base.py` helper extracted + `h_pp_source_blend.py` Stage 0 HOLD |
| r | 08d1763 | `pirate_l1_log.json` per-tick shipped + `h_chp_midlead_regression.py` pre-built + ran → ESCALATE + `h_pp_platt_by_regime.py` HOLD (frontal MARGINAL_DRIFT sub-signal) |
| s | 2da8523 | `h_ch_persistence_blend_stage2_vs_l6.py` (chp Stage 2 rebuilt vs L6 baseline; honest SHIP set 5 cells vs 28 live) + `h_pp_frontal_platt_stage1.py` → SHIP |
| t | 620f882 | chp emergency demote of 6 clear-regression cells (curated JSON edit + emergency_demotes audit block); collector deployed 00:06Z |
| u | afd360c | debug page sweep for q/r/s/t |

## Marquee findings

### 1. First shippable pp correction — frontal × 6-11h Platt

- `h_pp_frontal_platt_stage1.py` — four halves-refit variants inside frontal-only population
- **`band_6-11_fix`**: fixing b=0.6 (per pooled slope-stability finding, |Δb|=0.06 across halves) unlocks clean SHIP
- Brier lift **-28.56% / -18.73%** across halves, |Δa|=0.20 (well inside 0.5 stability gate), n=292
- Every other variant HOLD; other bands blow up numerically (Newton pathology on ~10% base rate + n≤587)
- Ceiling from PM session's Reliability decomposition (~5% pooled) doesn't apply — frontal-6-11h subpopulation has fundamentally different (more consistently under-forecasting) calibration than pooled
- **Design that Stage 3 will wire**: `σ(a_t + 0.6·logit(raw))` only when `state_fc.regime_synoptic == "frontal" AND lead_h ∈ [6, 11]`; refit `a_t` on rolling 30-day frontal-6-11h window (Fitter cadence)
- **Stage 2 next**: walk-forward evaluation before wiring. n=292 tight; want 3-5 more frontal passages. Earliest wire ~08-03.

### 2. chp Stage 2 was measured against the wrong baseline

Chain of discovery:
1. **`h_chp_midlead_regression.py`** (pre-built ahead of 07-28 Calendar trigger; ran against live data) → **FIRES ESCALATE**. 6 leads (10-15h) exceed the +20% trigger with n=176-186 per lead. Peak lead 12 = +30.1% (chp 16.37 vs L6 12.59).
2. **`h_ch_persistence_blend_stage2_vs_l6.py`** (fork of shipped Stage 2 — original untouched). Uses `forecast_l6` as baseline instead of `forecast_l4`; post-Lc-flip window only (07-17 → 07-27, 10 days). Shows honest SHIP set is **5 real cells** (calm/0-5 −70%, pre_frontal/0-5 −41%, sw_flow/0-5 −30%, se_flow/0-5 −26%, ne_flow/6-11 −17%) vs 28 currently live. **11 live cells flip → SKIP** (worst sw_flow/24-47 +59%).
3. **v0.6.382t emergency demote** — 6 clear-regression cells (both halves worse, n≥100, Δ ≥ +28%): sw_flow/24-47 (+59%), sw_flow/12-23 (+38%), sea_breeze/24-47 (+37%), pre_frontal/24-47 (+32%), se_flow/6-11 (+29%), ne_flow/12-23 (+28%). Curated JSON edit with `emergency_demotes` audit block. Rollup 19/9/7/2 → 14/8/13/2. Deployed 00:06Z.
4. **Full-shape adoption** (adopt the 5-cell SHIP set entirely, drop the remaining 5 halves-disagreement / small-magnitude cells) — pending normal 7-day live-layer change gate. Day 1/7 as of 07-28.

Class of bug: same as [[project_cc_sat_correction]] 07-20 kill (measured against wrong baseline → shipped a regression → same-day fix). See [[feedback_measure_against_live_stack_baseline]].

## Other ships (non-marquee)

### persistence_gate_base.py helper (v0.6.382q)

New `weather_collector/processors/persistence_gate_base.py`. `SpecialistSpec` dataclass + `run_specialist()` fn factoring out the boilerplate shared by chp/clp/wdp. **Shadow-write invariant baked in** (per v0.6.382p bug fix) — future clones cannot regress. Covers both concrete shapes:
- `post_obs_bypass_context` — chp/clp shape (regime = state_curr, same all leads)
- `predicted_transition_context_factory(fc_regime_for_lead_fn)` — wdp shape (per-lead fc_regime + transition check)

Not migrating chp/clp/wdp today (mid-watch; no-churn rule). Next specialist (wgp/dpp/...) uses helper as one-liner registration.

### pirate_l1_log.py (v0.6.382r)

New processor. Extended `fetchers/pirate_weather.py` to extract `hourly_precip_probability` (already fetched but unused). Wired into `collector.py` after GFS spread snapshot. 14-day GCS retention. Post-deploy: file exists at `gs://myweather-data/pirate_l1_log.json`, 382 bytes at first tick.

Starts the clock for 3-source pp source-blend re-test — earliest 2026-08-10 when the log has 14 days of coverage. Booked after `h_pp_source_blend.py` HOLD (HRRR+GFS near-collinear; α → ~1.0, Brier Δ = 0.00%; both models post-process from the same NCEP soup).

### clp gate EXTENDED 07-31 → 08-03 (v0.6.382q)

Post-shadow-write-fix follow-through. Pre-fix, the 7-day gate through 07-31 was reading zero real data. Fix landed evening PM (v0.6.382p); newly-valid data starts 07-28. Extended to 08-03 for a full 7 daily reads. Updated: `cl_persistence_gate.py:41` comment, 5 debug-page sites, JS SPECIALIST_STACK comment, Calendar 08-03 row, TODO + investigation memory.

### h_pp_source_blend.py Stage 0 HOLD (v0.6.382q)

Booked from PM session as the attack-Resolution-term candidate. 23,232 pair-log rows joined with gfs_l1_log by (run_hour, valid_time). Weighted: α → 0.89 / 1.00 across halves, Brier Δ = 0.00%. Logistic Newton needed ridge damping for collinear features; ridge-stabilized read half A→B = −2.94% (below 5% ship gate). Physical finding: HRRR + GFS pp near-collinear. Follow-up requires Pirate historical logging — shipped same session (see above).

### h_pp_platt_by_regime.py Stage 0 HOLD + frontal sub-signal (v0.6.382r)

Regime-conditional Platt fits inside each `state_fc.regime_synoptic` bucket. Aggregate weighted-by-n WORSE by +21% / +25% — pooled non-stationarity was different miscalibration signs across regimes canceling out. **Frontal was the one positive sub-signal** (MARGINAL_DRIFT, both halves −15% Brier, |Δa|=0.66). Every other regime got worse with recalibration. Calm blew up numerically (b → 2726, class-imbalance edge case). Design seed → became evening-3's SHIP.

## Numerical trap flagged (recurring across pp scripts)

Newton on logistic with collinear or class-imbalanced features diverges without ridge damping. Bit both `h_pp_source_blend.py` (HRRR+GFS collinearity) and `h_pp_platt_by_regime.py` (calm regime = zero positives in one half). Ridge `λ = 1e-3 · n` on Hessian diagonal rescues collinearity but NOT class-imbalance (with zero positives the gradient scales differently). Future pp scripts should include a minimum-positive-count check per subpopulation (skip if either half has < 20 positives).

## Session commits

- v0.6.382q → 8e99fd6
- v0.6.382r → 08d1763
- v0.6.382s → 2da8523
- v0.6.382t → 620f882 (frontend push) + collector deploy at 00:06:13Z
- v0.6.382u → afd360c

Frontend pushed to Pages. Collector deployed after v0.6.382t (curated JSON change is a live-behavior update; other backend adds — `persistence_gate_base.py`, `pirate_l1_log.py`, `pirate_weather.py` extension, collector.py Pirate wire — activated same deploy). No further deploys needed for u.

## Related

- [[project_07_27_session]] — AM (wdp flip + debug page passes)
- [[project_07_27_pm_session]] — PM (pp recalibration ceiling + shadow-write bug fix)
- [[project_pp_recalibration_session]] — updated with source-blend HOLD + frontal Stage 1 SHIP
- [[project_chp_midlead_regression_watch]] — updated with L6-baseline Stage 2 rebuild + emergency demote
- [[feedback_persistence_gate_shadow_write]] — invariant now enforced by `persistence_gate_base.run_specialist()`
- [[feedback_measure_against_live_stack_baseline]] — chp Stage 2 vs forecast_l4 fell into this class
