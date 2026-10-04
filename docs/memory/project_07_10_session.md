---
name: project-07-10-session
description: 2026-07-10 marathon session. 9 commits. Silent-dormancy audit sweep (streak-infra, LC/C1h/C1d gate counters, C1 gate-firing coverage). Odometer built + rebuilt after big bug. Difficulty conditioning framework. Ended with the "am I measuring the right thing" audit that shipped RMSE + bias to the scorecard.
metadata:
  node_type: memory
  type: project
  originSessionId: current
---

## Session arc

Started as a check-in on the 07-09 marathon. Ended as a fundamental audit of "what are we actually measuring?" Nine commits across two categories: (1) silent-dormancy hardening — plugging every "day N/7" aspirational-text gap, (2) measurement framework — added RMSE + bias to the scorecard so it matches how NWS/ECMWF actually score forecasts.

## Ships (9 commits)

- **v0.6.320** — Digest streak-infra dormancy fix. The L3-drop-ws whitelist streak had been silently wedged at 0/7 for 7 consecutive days because `claims.py::_claim_walkforward` was reading a stdout-redirected .log that was subject to Python's block-buffered stdout at child-exit. Fix: fallback to `walkforward_l3l4_summary.txt` (direct-flush), killed a duplicate parser in `divergence_report.py`, added dormancy guard (skip null-claim rows when source verdict is populated), fixed `_streak_for` to filter today by UTC date rather than `rows[:-1]`. Backfilled today's row. Earliest ws L3 strip pushed from "07-10 (fictional)" to actual 07-16.
- **v0.6.321** — C1h per-cell co-axis ortho gate. First `h_c1h_orthogonality` live-digest read gave overall PROMOTE (11 ortho / 30 judged) but per-cell only cl × 3 bands are ortho to both C1f and C1e. Wired `_C1H_CO_AXIS_GATE` in `confidence_layer.py` instead of pruning the curated table: cl fires freely, cc/cm/ch conditionally suppressed based on which co-axis they're non-orthogonal to; ch 24-47h + t × 3 bands never fire (REDUND to both). New `coax_gated` state distinct from `flat` in telemetry. Live-verified at the :17 tick.
- **v0.6.322** — `h_ws_octant_bias.py` Stage 0. First read: HRRR over-forecasts moderate+ ws by +0.9 to +1.9 mph on SW/S/E/NE octants, near-zero on NW/N/W. Joe corrected the geography — NW/N/W come across water for the last stretch (not land friction as I first framed). Queued as Stage 1 candidate; 3 weekly re-reads then Stage 1 script.
- **v0.6.322a** — Debug canon refresh sweep for today's earlier ships. Recent activity block rotated. C1 confidence section updated to retract the v0.6.316 "⚠ Scope note" that today's v0.6.321 ortho gate resolved. Stage 1 candidate count 5 → 7.
- **v0.6.323** — Silent-dormancy audit Part 2: three more aspirational-text gates wired with real counters. LC_ENABLED gate had no `_claim:LC_ENABLED` writer (divergence report rendered "GATED 1/?" literally — the "?" was because there was no gate). C1h and C1d narrow-promote gates had no counters either. All wired: `_claim_lc_enabled()` + `_claim_marginal_ship_cells()` in `claims.py`; new "Narrow-promote gates" section in the digest exec summary walks the streaks. Also owned two false alarms: post-ship 14-day watch (exists, works), frontal events log (writes conditionally by design). Also wired C1 gate-firing coverage: `confidence_layer.py` now calls `gate_firing_log.record_firing()` for C1h + C1d — live-verified at the :17 tick with `op=C1h` in the log.
- **v0.6.323a** — Canon sweep after the counters ship. Every "day N/7" reference on the debug page updated to reflect real counters (not aspirational text). Historical timeline block rewritten to acknowledge what actually happened 07-10 (sr suppression closes tonight → clean read 07-11; ws L3 strip didn't ship because gate was fiction, earliest now 07-16).
- **v0.6.324** — `production_regime_trajectory.py` — the odometer. Answers "is the pipeline getting better vs weather-favorable" by writing per-(day, regime, field) Production %-vs-raw to a rolling JSONL. Bootstrapped 28 days of history on first run.
- **v0.6.324a** — CRITICAL BUG FIX in the odometer. The pair-log `forecast` field is captured at pair-log time; for L2-additive fields (dp/h/t/ws/wg/pr) `forecast == forecast_l4`, but for fields where the correction runs later (cc/cl/cm/ch under L3/L4, sr under Lsr, pa) `forecast == forecast_l1` (raw). My odometer used `forecast` as Production. For 6 of 12 fields I was comparing raw to raw. All my "cloud fields are flat per day" numbers were noise. Caught by Joe with a pointed question ("I just care whether my forecast beats raw — am I wrong?") that made me spot-check the field semantics. Fix: `fc_prod = forecast_l4 or forecast_l3 or forecast_l2 or forecast_l1 or forecast`. Deleted + rebuilt JSONL. Corrected 28-day per-field numbers: wg −35%, ch −33%, ws −17%, dp −16%, cc −8%, h −7%, cm −5%, t −2%, sr −1%, pr −0.6%, cl −0.1%, pa 0%, pp +20% worse.
- **v0.6.325** — Scorecard now measures what real weather models measure. Joe pushed on "am I measuring the right thing?" Walked through NWS/ECMWF verification conventions. Phase 1 added RMSE + bias accumulators to `decay_fit.py` (per_layer_sq, per_field_prod_signed, per_field_prod_sq); emit `per_layer_rmse_by_lead` in time_series_diagnostic.json; scorecard banner rewritten to show MAE mean + RMSE mean + MAE median at "Overall vs raw"; biggest gain/regression tiles show MAE% (primary) + RMSE% + bias in field units; reader-facing prose explains what each metric answers, names the local-network observations, honestly labels what's not yet measured (persistence skill, pp reliability decomposition). RMSE will populate visually after next Fitter tick (03:07 EDT 07-11). Hand-computed preview: wg MAE −33% but RMSE −26% (7pp gap); dp/h/ws smaller gaps; pp MAE +20% but RMSE −3% (23pp gap — MAE is the wrong metric for pp).

## Non-code work

- **Debug page framework rewrite** (in prose, not tile logic yet): added a "How we measure whether the forecast is good — the metric framework" collapsible section between the priority scoreboard and Engineering Updates; updated the Accuracy section prose with a metric caveat noting MAE-only + RMSE gap for L2-additive-bias fields; updated Stage 4 audit prose to acknowledge it's MAE-only scored; updated state-stratified section prose similarly. Documented the two-metric disagreement, named the persistence + climatology gaps, called out that "observed" is a local-network estimate not ground truth.

## Investigation arcs (Stage 0 explorations that did or didn't ship)

- **Difficulty conditioning** (production_trajectory_by_difficulty.py): L2-additive-bias fields show massive Q1-Q4 raw-MAE-quartile variation. dp Q1 easy days: pipeline HURTS +4% to +26%. dp Q4 hard days: HELPS −6% to −44%. Same pattern for h, ws, wg. Cloud fields more uniform. Expected signature of well-calibrated bias correction — not a bug.
- **Stage 4 difficulty lens** (c1_stage4_difficulty_lens.py): checked whether Stage 4 drift is confound with weather shift between calib and recent windows. Result: 44 of 104 cells (42%) are weather-confound (Production and Raw drifted together — not a calibration miss); only 8 cells (8%) are real drift. Informs tomorrow's 07-11 Stage 4 re-check.
- **h_raw_error_predictors.py**: for each field × forecast-time predictor, does the predictor separate raw MAE AND does correction help scale with predictor? fc-magnitude-Q was the strongest predictor across L2-additive fields (2-6× raw MAE elevation). Multiple ★ REAL predictors identified.
- **dp_c1f_gate_stage1.py** — Stage 1 KILLED. Stage 0 said "dp × C1f p1 rows have local hurt of −0.017°F." True locally. But p1 fires only 7.7% of dp pairs. Aggregate improvement from skipping: 0.06%. Not worth shipping. Lesson: Stage 0 elevation ratio measures correlation, not aggregate impact — a predictor can perfectly identify hard vs easy AND fail to justify a gate if the "hard bin" is a small share of pairs.

## Framework decisions

- Binary skip-gates don't work well for small-share bins. K-scaling (continuous magnitude modulation) generalizes better but is more code.
- Regime-diversity gate for narrow-promote (requiring 7-day windows to include ≥2 distinct dominant regimes) was proposed. Not built. Deferred to next session.
- The "raw-MAE-decile lens on the odometer" is queued as the next architectural move for the odometer specifically.

## Roadmap coming out of the session

**Immediate (07-11 morning):**
- 03:07 Fitter fires → scorecard tiles populate with RMSE + bias — verify visually
- 06:22 digest fires with Stage 4 re-check + sr clean read + sr_shortwave_cc_confound first read
- Stage 4 difficulty lens auto-runs

**Saturday afternoon or next session:**
- Rewrite the Accuracy section table (MAE + RMSE + bias columns per layer, not just MAE)
- Phase 2: persistence baseline. `h_persistence_skill.py`. ~2-3 hours. Joins pair-log with obs_temp_log to get obs at run_time; scores forecast against "same as it is now." Answers whether the pipeline actually adds value at short lead where persistence is a strong baseline.

**Later:**
- Phase 3: pp reliability decomposition (Brier into reliability + resolution + uncertainty).
- Phase 4 (optional): climatology baseline.
- Threshold-based scoring IF Joe identifies specific yes/no decisions he makes from the forecast.

## Rules codified

- [[feedback-forecast-verification]] — how real weather models are actually scored. What we measure and don't measure.
- [[feedback-co-owner-posture]] extended with the "I keep missing the meta-question until Joe asks it" pattern. Two catches by Joe today: (1) the odometer bug (I was measuring the wrong thing for 6 fields), (2) the RMSE gap (I claimed "same summary math" without checking). Co-owner failure signature: I stayed inside the frame instead of asking "is this frame right?"

## Related

[[project-07-09-session]], [[project-todo]], [[feedback-co-owner-posture]], [[feedback-forecast-verification]], [[feedback-streak-infra-dormancy]], [[feedback-verify-writers-for-read-paths]]
