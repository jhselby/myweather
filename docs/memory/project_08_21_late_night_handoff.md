---
name: 08-21-late-night-handoff
description: "08-21 late-night session close — 16 ships v0.6.450-465. NBM cascade at TRUE feature parity with HRRR (F3-F8 + regime cross-cut + first curated skip cells + dp drop). Tomorrow morning: paste digest and evaluate whether dp Prod dropped to match dp raw_nbm as expected."
metadata: 
  node_type: memory
  type: project
  originSessionId: 3686728f-c756-4644-9af6-ccbb2487150d
  modified: 2026-08-22T00:37:16.310Z
---

# 08-21 late-night handoff — NBM at TRUE feature parity, dp fix live, wait for tomorrow's digest

**READ THIS FIRST — this is the entry point for the next session.**

## Session shipped (16 versions, all deployed + verified)

- **v0.6.450-455** — cc L3_NBM clamp; L4_NBM (cc/ch); L5_NBM (sr); L6_NBM scaffold (t, ENABLED=False); chp_nbm (ch); debug page F1-F12 punch list.
- **v0.6.456 (F3)** — applied_layer stamp NBM-aware; chp_nbm/wdp_nbm distinct layer keys; l6_nbm_fit uses pair_log_paths().
- **v0.6.457 (F1+F2)** — `analysis/nbm_regression_sentry.py` + `analysis/nbm_walkforward_validator.py`; both surface in digest exec-summary.
- **v0.6.458 (F4+F5)** — gate_firing_log NBM operators (L3_NBM..WDP_NBM); `skip_table_nbm_curated.json` + `skip_table_nbm.py`.
- **v0.6.459** — debug page sweep for F3/F4/F5.
- **v0.6.460 (F6)** — PWA writeback: `_SELECTOR_WRITEBACK` map overwrites `hourly[array_name]` for selector-picks-NBM rows. Users had been seeing HRRR-corrected values on cells the selector picked NBM (wg 12-47h, dp 6-47h, cc all leads); fixed.
- **v0.6.461 (F7+F8)** — `describe_applicability()` on l3/l4/l5/l6_nbm + skip_table_nbm; new `nbm_common.py` with CAPS_NBM + STALE_DAYS_NBM=7 + `cap_correction()` + `is_stale()`. Each NBM applier now clamps corrections + becomes no-op if stale.
- **v0.6.462** — walkforward regime cross-cut: `paired_by_regime[(field, cand, base, band, regime)]`. Emits per-regime SKIP proposals with real regime labels instead of pooled `"*"`.
- **v0.6.463** — first curated NBM skip cells: `dp l3_nbm 0-5h × {pre_frontal, sw_flow, se_flow}`.
- **v0.6.464** — closed `mae_over_time.L1_ONLY_FIELDS` NBM-attribution gap (wd path).
- **v0.6.465** — **dp dropped from L3_NBM_FIELDS entirely** (see below).

## The dp fix that mattered (v0.6.465)

Fresh per_field_scoring (10:00 UTC file was 14h stale) revealed dp Prod=2.895 vs NBM raw=0.841 — correction stack was making dp **244% worse** than raw NBM at leads where selector picks NBM (6-47h). Root cause: L3_NBM subtracts pooled +1°F bias fitted globally; NBM dp is already well-calibrated at Wyman Cove (bias ≈ 0, fc_std matches obs_std). Wrong-direction pooled bias worsens every regime. Same reason HRRR excludes dp from L3_FIELDS.

**Fix:** dp removed from `L3_NBM_FIELDS`. dp NBM cascade now `raw_nbm → l2_nbm` (identity since dp has no HRRR L2 delta).

**Yesterday's dp 0-5h skip cells retracted** — redundant post-drop. Moved to `history` block in curated JSON for provenance. Loader ignores history block.

**Expected in tomorrow's digest:** dp Prod should drop from ~2.9 → ~1.4 (matching raw_nbm) at 7d, and from ~2.9 → ~0.9 at 24h. If it doesn't drop, either the collector deploy didn't take or a further path is stamping dp_l3_nbm.

## Data collection audit passed

Deep-dive on "NBM raw crushes HRRR raw" numbers: matching timestamps, sensible ranges, consistent bias direction across lead bands. **HRRR L1 has real systematic biases at Wyman Cove** (h under -10%, dp under -2°F, sr under -60 W/m², t over +1°F). NBM is more physically calibrated. Our HRRR correction stack exists specifically to eat these biases. The mistake with L3_NBM+dp was adding a pooled correction ON TOP of already-calibrated NBM raw.

See [[user-wyman-cove-hrrr-l1-biases]] for the calibration reference table.

## Remaining differences HRRR vs NBM (real, not stale)

Every code path that reads pair-log residuals now routes NBM-served rows correctly. **True feature parity except:**
1. **Field scope, permanent** — cl/cm/pp/pa/pr HRRR-only forever (NBM grib doesn't carry).
2. **L6_NBM ENABLED=False** — pending "does NBM L2 double-count waterfront?" empirical investigation.
3. **skip_table_nbm_curated.json empty** — 41 walkforward proposals awaiting 08-28 review (see [[nbm-skip-proposals-review]]).
4. **NBM pair-log historical depth** — l4/l5/chp/wdp_nbm only started stamping 08-21; sentry sustained window will read THIN on those for another week. F3-D backstamp still deferred as low-ROI.

## Open questions for tomorrow's digest read

- **dp Prod dropped as expected?** (Primary sanity check — direct v0.6.465 verification.)
- **F1 sentry — anything HOT beyond expected THIN cells for l4/l5/chp/wdp_nbm?**
- **F2 walkforward divergence — do the DROP recommendations for cc/ch/sr/wg/t/ws/h stabilize as more live rows accumulate?** Some may be real like dp was; others may be identity-filter noise.
- **cc 24h regression watch** — 08-21 24h cc Prod (23.14) was worse than raw HRRR (17.57) on a flat-overcast day. If it persists 3+ days into 7d, F1 will fire HOT — expected behavior.
- **sr 24h same pattern** — Prod 94.77 vs raw 85.03. Small-sample flat-day.
- **h/t/wd selector opportunity** — NBM raw beats HRRR Prod at 24h by 40-50% for t and h. Selector picks HRRR everywhere because Prod-vs-Prod comparison is close (HRRR corrections eat most of HRRR raw's bias; NBM's l3 corrections may add noise). Worth walkforward re-look post-08-28 as NBM L3 fits stabilize on clean rows.

## Recent-activity chronology

- 08-19 v0.6.435 — L3_NBM scaffolded.
- 08-19 v0.6.437 — wdp_nbm, selector_source stamping begins.
- 08-20 v0.6.443-446 — backstamp end-to-end, selector armed, 9 cells flip NBM (wg 12-47h, dp 6-47h, cc all leads).
- 08-21 v0.6.450-455 — cascade completion (L4/L5/L6/chp_nbm) + debug sweep.
- 08-21 v0.6.456-461 — F3 audit, F1/F2 monitoring, F4/F5 gate+skip, debug sweep 2, F6 PWA, F7 applicability, F8 caps/staleness.
- 08-21 v0.6.462 — walkforward regime cross-cut.
- 08-21 v0.6.463 — first NBM skip cells (dp 0-5h) — later retracted.
- 08-22 v0.6.464 — L1_ONLY gap closed.
- 08-22 v0.6.465 — dp dropped from L3_NBM_FIELDS.

## Files touched (summary)

**New:** `weather_collector/processors/nbm_common.py`, `weather_collector/processors/skip_table_nbm.py`, `weather_collector/data/skip_table_nbm_curated.json`, `analysis/nbm_regression_sentry.py`, `analysis/nbm_walkforward_validator.py`.

**Heavily modified:** `weather_collector/processors/forecast_snapshot.py` (F3-A/B applied_layer + specialist keys + F4 gate telemetry + F5 skip gates + F6 writeback), `weather_collector/processors/forecast_error_log.py` (chp_nbm/wdp_nbm layer tuples), `weather_collector/processors/l3_nbm.py` (F7+F8+dp drop), `weather_collector/processors/l4_nbm.py`, `l5_nbm.py`, `l6_nbm.py` (F7+F8), `weather_collector/collector.py` (F7 aggregation), `analysis/l6_nbm_fit.py` (pair_log_paths), `analysis/l1_selector_fit.py` (already had it, this session verified), `analysis/mae_over_time.py` (v0.6.464 L1_ONLY NBM), `analysis/runlog/build_executive_summary.py` (F1/F2/F5 hooks), `corrections_debug.html` (three sweeps), `docs/CHANGELOG.md`.

## Related memory

- [[nbm-structural-completion-plan]] — the plan of record; now largely SHIPPED. See "Real remaining differences" above for what's not.
- [[nbm-skip-proposals-review]] — scheduled 2026-08-28 review of the remaining walkforward SKIP proposals.
- [[user-wyman-cove-hrrr-l1-biases]] — HRRR L1 systematic bias reference (h -10%, dp -2°F, sr -60, t +1°F).
- [[feedback-refresh-current-state-before-defending]] — the lesson from today's dp incident.
- [[08-21-evening-handoff]] — superseded; kept for chronology.
