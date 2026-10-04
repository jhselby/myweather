---
name: project-07-31-session
description: "2026-07-31 session log. 6 ships (v0.6.390e/f/g/g-hotfix/h + 2 debug/analysis follow-ups) + 1 collector deploy. Marquee: h L2 station_bias shape retune after regime shift on 07-25 (v0.6.390g, floor 0.4→0.1, end 24→10). Also: caught both sentries had been silently offline since ship (v0.6.390e), landed sustained-vs-fresh 4-verdict regression sentry (v0.6.390f), resolved cc architecturally as derived-with-tunable-composition + confirmed via pure composition analysis (max wins 9/10 regimes, 1.6-pt bias vs METAR), digest cleanup 13 scripts retired (v0.6.390h)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 434af779-9797-4cea-bd88-1e0939ffeef0
  modified: 2026-07-31T15:41:30.201Z
---

# 2026-07-31 session

**6 ships + 1 collector deploy. Big net win.**

## Ships in order

- **v0.6.390e** — sentry sys.path fix. Both sentries (regression v0.6.389i + layer-shape v0.6.390d) had been silently returning "unavailable" every digest since ship. Root cause: `run_digest.sh:85` invoked `build_executive_summary.py` via direct path (`python3 "$TOOL_DIR/…"`), setting `sys.path[0]` to `analysis/runlog/` instead of repo root. Inline `from analysis._cache import cached_path` inside sentries threw `ModuleNotFoundError`, swallowed by try/except → "unavailable" message. Fix: swap to `python3 -m analysis.runlog.build_executive_summary`. Same for `divergence_report`. Also new: `h_cc_blend_formula.py` Stage 0 tuner comparing max / random / max-random overlap formulas per regime (verdict: STAGE 0 HOLD, max wins 8/10 regimes). Architectural resolution: **cc is derived-with-tunable-composition** — no independent L1/L2/L3/L4/Lc corrections on cc; Ccd owns composition (currently max, may become regime-conditional); cc still measured daily as tuner input + drift detector. See [[project_cc_derived_field]] updated with three-position framing, [[project_cc_blend_tuner]] NEW.
- **v0.6.390f** — regression sentry rewritten as sustained (7d) + fresh (3d) 4-verdict classifier (⚠ SUSTAINED FIRE / ✓ HEALING / 🔥 FRESH FIRE / clean). Flat-window sentries lag interventions by their width; pair keeps sustained + current-state separate and turns divergence into diagnostic. First live run: cl SUSTAINED FIRE (07-30 catastrophe still dominates 3d), cc FRESH FIRE (cascade via max). See [[feedback_ratio_over_absolute]] updated with pair-window refinement.
- **v0.6.390g** — h L2 station_bias shape retune. `H_SOFT_RAMP_FLOOR: 0.4→0.1`, `H_SOFT_RAMP_END: 24→10` in `corrected_hourly.py`. See [[project_h_l2_shape_retune]] for full investigation, decision, watch triggers.
- **v0.6.390g hotfix** — f-string backslash syntax error in `h_l2_shape_sweep.py` blocked collector build. `f"  {'floor \\ end':<12}"` → precompute label as var. Trivial.
- **v0.6.390h** — digest cleanup. 13 scripts retired via .py.skip rename; 1 registry entry added. See "Digest cleanup" section below.
- **Debug page footnote soften** — cc scoreboard "not in mean" text reframed to acknowledge composition tuning path.
- **Pure composition analysis + footnote numbers** — `h_cc_composition_pure.py` NEW: applies each formula to OBSERVED components, compares vs observed cc, strips cascade. Finding: max wins 9/10 regimes, pure MAE 1.6 pts, bias −1.6 (systematic under-report vs METAR). Documents concretely why cc stays out of scoreboard mean today. See [[project_cc_composition_pure]] NEW.

## Marquee investigation: h L2 damage since 07-25

**Symptom:** layer-shape sentry (after we fixed it) flagged h/production τ-suspect ★ — helps 0-5h (−16.6%) but hurts 6-11h (+14.8%), 12-23h (+11.0%), 24-47h (+8.8%).

**Diagnosis path (with detours):**
1. Wrote `h_h_dp_tau_refit.py` — first version used `error` field as baseline. Bug: `error` in pair log is PRODUCTION residual (`forecast - obs` where `forecast` is applied), NOT L1 residual. My baseline was already-corrected. Fixed to `error_l1`. See [[feedback_pair_log_error_field]] NEW.
2. Fixed baseline showed all τs hurt for h+dp. Joe pushed back — pointed out L3/L4 whitelists exclude h and dp entirely, so L2 IS production. Wrote `h_h_dp_layer_walk.py` — direct measurement of per-day per-layer marginal contribution. Confirmed: L3=0.0% marginal for h/dp (not applied); L4 ≤5% marginal. **All action is in L2.**
3. Layer walk revealed h's L2-vs-L1 marginal was consistently helping (−5% to −25%) through mid-July, then flipped POSITIVE (+6% to +36%) starting **exactly 2026-07-25**. Same shape for dp.
4. Located h L2 mechanism in `corrected_hourly.py`: `corrected_humidity[lead] = raw_h[lead] + humid_bias × soft_ramp(lead)` where soft_ramp has FLOOR=0.4, END=24 (shipped v0.6.218, calibrated 2026-06-22). **dp is 100% Magnus-derived** from corrected_t + corrected_h — no independent bias correction; dp damage inherits h damage.
5. Ran `h_humid_bias_trajectory.py` — reconstructed daily humid_bias from `l2 - l1` at lead=0. Result: bias oscillates ±0.5-2% with frequent sign flips (5 in last 8 days). Applying 40% of a sign-flipping bias for 24+ hours forward = noise injection.
6. Ran `h_l2_shape_sweep.py` — full grid across floor ∈ {0.0..0.4} × end ∈ {6..24}, halves-verified on top-5. **7d window best: {floor=0.0, end=8}. 14d window best: {floor=0.4, end=12}.** Grids INVERT between windows because 07-17 → 07-24 (old regime) is only in the 14d window.
7. Joe chose middle path {floor=0.1, end=10} — beats old shape on BOTH windows: +2.8% vs raw on 7d, +6.0% vs raw on 14d. Reversible one-line edit. Watch: h L2-vs-L1 marginal in daily digest, should stay negative for 5+ days.

**Also discovered while investigating:** shadow whitelist tuner has been intermittently recommending "add h to L4" across 12 daily Fitter cycles (2026-06-17 → 06-30 heavily, then quiet, then 07-27 + 07-28 again). We've never adopted it. dp has NEVER been shadow-recommended for L3/L4 in 45 cycles — genuinely L2-only-forever. Parked as separate workstream from L2 shape fix.

## cc architectural conversation

Joe pushed hard on the framing. Sequence:

1. Layer-shape sentry showed cc/production +25% at 0-5h, +26% at 6-11h. My initial reaction: "cc is hurting."
2. Joe: "cc has been removed from all scoring." Correct — v0.6.390 excluded cc from scoreboard aggregate.
3. But cc IS still displayed (Right Now, briefing) and IS scored in `time_series_diagnostic.json`. Different from "not scored anywhere."
4. Joe pushed: is cc independent (correctable) or purely derived (frozen)? I flip-flopped, first "retire entirely" then "tune the overlap formula" — contradictions.
5. Joe called it out: if formula needs tuning, cc has structure worth learning, not purely derived.
6. **Landing: cc is derived-with-tunable-composition.** No independent L1/L2/L3/L4/Lc corrections; Ccd owns composition; composition is regime-tunable if signal appears.
7. Empirically verified raw HRRR cc = max(cl, cm, ch) 20/20 rows — HRRR uses max-overlap as its native TCDC convention.
8. Ran Stage 0 tuner. Max wins 8/10 regimes (frontal random +4.3% halves-unstable, nor_easter random +30.9% but data one-sided). STAGE 0 HOLD.
9. Then Joe pushed AGAIN: "if we own the formula and obs are independent, we ARE measuring something."
10. He was right. My "cascade double-counting" argument was too strong. Composition error IS a real independent quantity. Ran `h_cc_composition_pure.py` — applies formulas to OBSERVED components, strips cascade entirely. Finding: max's pure composition MAE = **1.6 pts, bias −1.6 (systematic under-report vs METAR)**. Wins 9/10 regimes. ~5% of obs magnitude, 2 orders of magnitude smaller than cascade error.
11. Decision: cc stays out of scoreboard mean today (composition signal drowned by cascade), but debug page footnote now names the concrete numbers and sets threshold for re-inclusion (≥3-pt composition error → add separate scoreboard line, not cc-in-mean).

## Digest cleanup (v0.6.390h)

Full audit of 143 running scripts. 13 retired to `.py.skip`:

**Kill (8) — dead investigations:**
- `h_c1g_orthogonality` — KILL verdict, 72/72 redundant
- `derived_humidity` — WASH "Shelve"
- `h_cl_linear_ramp_stage2` — SUPERSEDED by cl_persistence_gate v0.6.379
- `l6_l2_double_counting` — Lc architecturally settled
- `h_pp_kalman_recalibrate` — HOLD; Platt/bin/source_blend peers cover
- `h_cloud_l4_sim` — Cloud L4 rejected; L3 (v0.6.366) covers
- `h_asymmetric_l3` — SUPERSEDED by v0.6.366 asymmetric SKIP
- `h_h_residual_persistence_stage1` — FAIL for weeks

**MLC suppress (5) until 08-06:**
- `marine_layer_anomaly`, `marine_layer_cl_stage1`, `marine_layer_stage1`, `marine_layer_stage2`, `marine_layer_collapse_diagnostic`

**Registry (1):**
- `h_cc_derivation` added to `KNOWN_LIVE_PIPELINES` in `build_executive_summary.py` (Ccd LIVE since v0.6.390; script auto-relabels STABLE)

**Deferred:** `pop_calibration` — 5-min read next session before deciding.

**Kept as background sensors:** 14 Stage 0 hypothesis scripts (`h_cloud_diurnal`, `h_cloud_floor_ceiling`, etc.) that hunt for future regime-shift signals. Cheap, cost ~140s total. Best long-term fix would be a "surface only on HIT" digest filter.

**Impact:** ~2.5 min off daily digest, 13 fewer verdict blocks in PER-SCRIPT FINDINGS, cleaner signal-to-noise.

## Other notable findings

- **cl bandage IS working.** 07-31 mae_over_time shows cl prod 33.35 vs raw 50.39 = −34% (recovering). Layer-shape sentry still fires on cl because 7d window includes 07-28/29/30 catastrophe. Will flip to HEALING (via new 4-verdict sentry) around **08-02** when 3 clean post-intervention days accumulate. Full sentry recovery ~08-06 when bad days roll out of 7d window.
- **Regime shift class.** Same pattern breaking Lc for cl on 07-30 also broke station_bias for h on 07-25. HRRR-side upstream change; static bias-learning against moving target = damage. Both fields needed intervention.

## Files touched (net)

- **Ships:** `analysis/runlog/{run_digest.sh, build_executive_summary.py}`, `weather_collector/processors/corrected_hourly.py`, `corrections_debug.html`, `index.html`, `sw.js`, `version.json`
- **New analysis:** `h_cc_blend_formula.py`, `h_cc_composition_pure.py`, `h_h_dp_layer_walk.py`, `h_h_dp_tau_refit.py`, `h_humid_bias_trajectory.py`, `h_l2_shape_sweep.py`
- **Retired:** 13 `.py` → `.py.skip` (see cleanup section)
- **Memory:** created [[project_cc_blend_tuner]], [[project_cc_composition_pure]], [[project_h_l2_shape_retune]], [[feedback_pair_log_error_field]], [[feedback_sentry_syspath_invocation]]; updated [[project_cc_derived_field]], [[feedback_ratio_over_absolute]], [[MEMORY]]

## Watches on the clock (session end)

- **08-02** — cl should flip SUSTAINED FIRE → HEALING in new 4-verdict sentry (if not, bandage isn't holding)
- **~08-05** — h L2 shape watch: L2-vs-L1 marginal should stay negative for 5+ days
- **08-06** — cl-recovery 7d window fully rolls off; MLC .skip re-enable trigger
- **08-07** — cc blend tuner re-check (frontal + nor_easter data accumulation); h L2 shape 7-day watch closes
- **08-11** — wind_blend BLEND_HOURS + wd L2 watches close

## Related

- [[project_h_l2_shape_retune]] — full h L2 investigation + shipped fix + watch triggers
- [[project_cc_composition_pure]] — 1.6-pt pure composition finding
- [[project_cc_derived_field]] — updated 3-position framing
- [[project_cc_blend_tuner]] — Stage 0 tuner + gate criteria
- [[feedback_pair_log_error_field]] — `error` is production residual, not L1
- [[feedback_sentry_syspath_invocation]] — sys.path[0] failure mode from direct-path invocation
- [[feedback_ratio_over_absolute]] — updated with pair-window classifier
- [[project_lc_regime_conditional]] — the 07-30 crisis that motivated the sentry infrastructure
