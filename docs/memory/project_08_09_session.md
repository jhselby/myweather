---
name: project-08-09-session
description: "2026-08-09 session. 3 ships (v0.6.398 fossil-window helper + v0.6.399 Lc recent-bias gate 7-day tracker + v0.6.399a scoreboard cl exclusion). NOTABLE — session ran hot on Claude side: 4 factual/arithmetic misses that user caught (pa/pp tau, cc in gate, C1h shipped, median arithmetic). User cut session and requested fresh instance. Two new feedback memories saved to codify the reflex gaps."
metadata:
  node_type: memory
  type: project
  originSessionId: 4497b339-2efa-4cc6-a9d8-ca9e374ecf4a
  modified: 2026-08-09T11:19:05.517Z
---

# 2026-08-09 session summary

## Ships (3 commits, all pushed)

1. **v0.6.398 — fossil-window bug class CLOSED.** New `analysis/_windows.py` with `rolling_windows(recent_days=15, prior_days=15, end=None)` helper returning `Windows` NamedTuple of A/B/FULL date-string bounds anchored at midnight-today. Migrated 14 fossil-prone analysis scripts: `h_ch_persistence_blend{,_stage2,_stage2_vs_l6}`, `h_cl_persistence_blend{,_stage2}`, `h_dp_residual_persistence_stage2`, `h_full_regime_sweep`, `h_l3_asymmetric_stage1`, `h_t_l2_regression_stage1`, `h_wd_persistence_gate_stage{1,2}`, `h_wg_l3_regression_stage1`, `h_wg_residual_persistence_stage2`, `h_ws_l3_regression_stage1`. `h_full_regime_sweep.py` is 2-window (A+B, no FULL) — handled by helper. `h_ch_persistence_blend_stage2_vs_l6.py` keeps its 5d/5d shape via `rolling_windows(recent_days=5, prior_days=5)`. The manual "slide 11 scripts +4d" ritual (documented 07-19, 07-22, 07-28, 08-01, 08-06, 08-08) is dead. `stale_window_audit` in `build_executive_summary.py` needed no change — once literals were gone from `WIN_*` assignments, tomorrow's digest reports "no fossil-window suspects" by construction. `[[feedback_fossil_windows]]` updated to CLOSED with pre-fix incident record preserved as history.

2. **v0.6.399 — Lc recent-bias gate 7-day rolling tracker.** Pipeline-to-good plan item #3 progress. `h_lc_recent_bias_gate.py` now appends each run's Stage 1 verdict to `.cache_lc_recent_bias_gate_history.json` (30d retention, 7d gate window) and prints a rolling gate summary — mirrors the `_append_gate_history` shape from `h_lc_regime_stage1.py`. Dropped **cc** from CLOUD_FIELDS — cc is derived via Ccd and never carries its own Lc shift (`[[project_cc_derived_field]]`); prior versions meaninglessly evaluated it. Today day 1/7: **ch = STAGE 1 PROMOTE** (halves +72.4%/+55.6% both positive), cl = HOLD-safe, cm = insufficient halves data. Gate clears earliest 2026-08-16 if ch stays promoted with no HOLD days. Gate-clear enables Stage 3 wire — modify `cloud_saturation_correction.py` to consult the gate per-cell before applying the shift on ch. No production code touched today.

3. **v0.6.399a — scoreboard `MAE_UNCORRECTED_FIELDS` adds cl.** cl's only MAE correction is the L2 hourly[0] blend at lead 0; scoreboard averages leads 1-47 by design. Counting cl in the touched median produced a structural +0.0% that dragged the median toward zero even when the correction stack was doing its job. Before: touched median = -1.6% (n=9). After: touched median = ~-3% (n=8). Main `MAE median · 7-day` still counts cl + pa + pr (reads -0.8%) — that's the wider "myweather vs raw across everything" story; touched is the correction-stack-effectiveness story. Split intentional.

## Debug page sweep (bundled with v0.6.399 commit)

- Recent activity: added 08-09 (Sun) entry; advanced 08-08 today→yesterday, 08-07 yesterday→2 days ago; trimmed 08-06 to CHANGELOG.
- Stage 1+3 candidates: bumped 10 → 11; added new **Lc recent-bias gate** entry with day 1/7 tracker + earliest wire date 08-16.
- Replaced 9 stale `"awaiting post-fossil-slide re-cut (windows advanced 08-05 v0.6.393b — next digest is first trustworthy read)"` phrases with `"verdict tracked continuously via auto-rolling windows (v0.6.398, 08-09)"` — reflects that v0.6.398 retired the hedge.

## Correctness incidents (4 misses, all caught by user)

Session was rough on precision. Documented as `[[feedback_verify_field_is_corrected]]` (3-check reflex before recommending correction-stack work) and `[[feedback_check_own_arithmetic]]` (sanity-check numbers before presenting them).

1. **pa/pp τ retune recommendation.** Included in "next steps" list. Both are L1-only in production (`[[project_pa_detection_gap]]`, `[[project_pp_recalibration_session]]`) — τ tuning affects only unused decay_corrections.json entries. User caught it; recommendation retracted.

2. **cc in Lc recent-bias gate.** First version of `h_lc_recent_bias_gate.py` post-tracker-migration had `CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]`. cc is in `_FIELD_SKIP` (derived via Ccd). User caught it same session; fixed to `["cl", "cm", "ch"]`, cache reset, promoted set corrected from `[cc, ch]` to `[ch]`.

3. **"Add C1h to KNOWN_LIVE_PIPELINES" housekeeping recommendation.** C1h had shipped v0.6.396 the same morning AND `h_c1h_orthogonality` was already in Auto-relabeled STABLE section of the same digest I was reading. Housekeeping task did not exist. User called it: "and c1h already done."

4. **Median arithmetic on scoreboard.** Presented list of 10 field %-vs-raw values, claimed median was pulled toward zero by pp (+0.0%), missed that scoreboard already routes pp to brierRows (excluded from MAE median calc). The three fields actually pulling the median were pa/pr/cl. User caught: "besides pp ALL of the fields have a better number than -0.8%." Re-read code, corrected, made the v0.6.399a fix.

User's read on the pattern: "I shouldn't have to look at a column of numbers and be able to see right away that your calculation is off. You should be ahead of me on that kind of thing, not behind me." Session ended with request for fresh Claude instance.

## New feedback memories saved

- `[[feedback_verify_field_is_corrected]]` — before proposing correction-stack work for field X: grep `_FIELD_SKIP`, check MEMORY.md for derived/L1-only status, git-log-grep for already-shipped items. Lists the trigger phrases that must fire the check.
- `[[feedback_check_own_arithmetic]]` — before presenting a computed number derived from a column the user can see: verify the arithmetic matches the visible data. If claim is "X pulls the value toward Y," check that X actually contributes to the calculation.

## Working tree state at session end

Clean working tree except for daily curated JSON drift (`weather_collector/data/*.json`, gate-history caches) — none committed today per `[[feedback_curated_json_daily_drift]]`. Untracked: `weather_collector/data/ch_persistence_gate_curated_vs_l6.json` (Stage 2 preview drift).

## Pipeline-to-good plan updates

- **Item #1 (h+dp τ refit)** — CLOSED as [deferred: no signal] 2026-08-09. Today's `h_h_dp_tau_refit` said STAGE 0 HOLD (neither h nor dp promotes on refit; best-τ either IS 14, gains too little, hurts a band, or halves-unstable).
- **Item #3 (cl root-cause fix)** — [in-progress: 2026-08-09]. ch cleared Stage 1 PROMOTE via recent-bias gate. v0.6.399 built the Stage 2 rolling tracker. Gate clears earliest 08-16.
- Items #2, #4, #5 unchanged.

## Non-actions checked

- dpbp day 5/14 — clean, no action.
- Lsb day 4/14 — MARGINAL Stage 1 today (halves diverge test/train) but pooled metrics dominate; watch continues.
- L6 Fix B rolling gate — 1 SHIP / 1 HOLD, CHURN, gate not cleared. Per `[[project_l6_fix_b_rolling_gate]]`.
- Lc recent-bias gate — day 1/7 with `[ch]` promoted, waiting.
- Regression sentry / layer-shape sentry / persistence-skill sentry — all clean.
- Anomaly detector — 9 WATCH but that's the cloud-difficulty week story per `raw_difficulty_index` (5 cloud fields harder than 90d baseline). Not the correction stack.
