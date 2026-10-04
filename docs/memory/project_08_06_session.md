---
name: project-08-06-session
description: "2026-08-06 session. 3 ships (v0.6.395 + 395a + 395b). Ships: c1 confidence re-curate (audit HOLD → 66.7% pass rate, wd cells CALIBRATED) + fossil-window slides on 3 h_* analysis scripts + debug page Rule 5 sweep + pp cell shows raw Brier value not meaningless MAE delta. **Discovery**: pp Platt frontal × 6-11h Stage 1 SHIP verdict from 07-27 has flipped to HOLD (|Δa| 0.20 → 1.15, halves sign-flipped, n dropped 292 → 226). pp calibration workstream now fully dormant. Non-actions: wsbp still HOLD; h L2 τ-suspect sentry clean; dpbp day 2/14; Lsb day 1/14."
metadata: 
  node_type: memory
  type: project
  originSessionId: 57d4089d-4089-4ad5-a9a4-2ee10689764d
  modified: 2026-08-06T17:31:14.863Z
---

# 2026-08-06 session summary

## Ships

1. **v0.6.395 — c1 confidence re-curate + fossil-window slides.** `c1_calibration_audit` flipped PASS → HOLD overnight (pass rate 52.6% < 75% threshold; wd 12-23h + 24-47h DRIFTED). Re-ran `c1_confidence_calibration.py` + `c1_curate_confidence_table.py` (v1 and v2) per audit's next-step. Pass rate 52.6% → 66.7%. wd cells DRIFTED → CALIBRATED; cl 12-23h + cm 12-23h remain DRIFTED — attributed to cloud-difficulty week per `raw_difficulty_index` (5 cloud fields harder than 90d baseline), not something more re-cutting fixes. Legacy cell counts: 15 SHIP / 4 MARGINAL / 37 SKIP → 14 SHIP / 6 MARGINAL / 36 SKIP. Also slid WIN_ constants +4d on 3 fossil-flagged scripts: `h_ws_l3_regression_stage1`, `h_wg_l3_regression_stage1`, `h_ch_persistence_blend_stage2_vs_l6`. All re-ran clean. Commit c17ee94.

2. **v0.6.395a — debug page Rule 5 sweep.** Recent Activity roll + Calendar date advance + wsbp status update + h L2 τ-suspect sentry-clean note for tomorrow's watch close.

3. **v0.6.395b — pp cell shows raw Brier value.** Per-field snapshot pp cells (7d + 24h) rendered `0.0% (Brier)` — delta always zero because nothing corrects pp value. Now shows raw Brier score (`660.48 Brier (L1 only)` for 7d, `5.85 Brier (L1 only)` for 24h). Auto-flips suffix to `(Δ−X.XX)` if any pp correction ever wires (Stage 3 landing target). Triggered by ad-hoc discussion → discovery below.

## Discovery: pp Platt frontal × 6-11h Stage 1 SHIP has flipped to HOLD

During the pp cell display discussion, checked `h_pp_frontal_platt_stage1` current verdict vs 07-27 SHIP:

- 07-27: n=292 |Δa|=0.20 pct=−28.56/−18.73 → SHIP
- 08-06: n=226 |Δa|=1.15 pct=+165.82/+5.27 → HOLD (sign flip + blow-up)

Same day `h_pp_platt_by_regime` HOLD (nw_flow + sw_flow coefficients unstable in the thousands); `h_pp_bin_calibration` flipped MARGINAL → HOLD. Full `[[project_pp_brier_reliability]]` workstream now dormant. pp is L1-only in production with no Stage 1 candidate holding. Memory `[[project_pp_recalibration_session]]` updated with re-check table.

## Afternoon: v0.6.395c → 395d revert arc + long framing discussion

**v0.6.395c** — Added native-units suffix to per-field snapshot cells (delta % plus absolute Prod MAE in native units). User noticed mixed units (% + °F/mph) confused the reader — the % delta answers "how much better than raw?" but native-unit MAE doesn't cleanly answer "how good is the forecast?" in a comparable unit. **Reverted in v0.6.395d.**

Extended discussion clarified the framing:
- Two genuine questions: "How is your forecast overall?" (standalone) vs. "How does your forecast compare?" (relative).
- Existing scorecard answers Question 2 with "vs Raw" — engineering credit for the correction stack.
- Question 1 has no truly standalone answer — every quality measure is implicitly a comparison to something. Best options: native units (reader supplies own baseline intuition), skill vs climatology (comparison to seasonal norm, wrapped in familiar language), or reframe to user's decision context.
- **Casual answer that works**: "12-13% better than the standard forecast for my area" (HRRR/GFS/NWS distinction immaterial to non-experts).
- **Methodology confirmed sound**: goal ("beat Raw") matches measurement (Prod vs Raw delta). Rare alignment.

## Big finding: `pp_brier_decomposition.py` ALREADY COMPUTES BSS vs climatology

I proposed building "BSS vs climatology for pp" as a new script; user asked if that generalizes across fields; user asked to just look at pp first; I went to build it and discovered `analysis/pp_brier_decomposition.py` line 121 has already been computing `brier_skill_vs_climatology = 1 - brier/uncertainty` for months. Should have searched first. See `[[feedback_search_before_proposing]]`.

### Results of running that existing script

pp raw BSS vs climatology per band (all bit-identical to corrected — pp is L1-only):

| Band | n | BSS | Reliability | Resolution | Uncertainty |
|------|---|-----|-------------|------------|-------------|
| 0-5h | 10,421 | **+36.2%** | 0.019 | 0.058 | 0.111 |
| 6-11h | 11,634 | **+35.5%** | 0.018 | 0.057 | 0.110 |
| 12-23h | 23,268 | **+45.6%** | 0.016 | 0.066 | 0.110 |
| 24-47h | 46,536 | **+46.2%** | 0.011 | 0.062 | 0.110 |
| Pooled | 91,859 | **+43.5%** | 0.012 | 0.060 | 0.110 |

**Interpretation**:
- Signal is real (+36-46% skill vs base-rate baseline).
- Correction budget is tiny: Reliability = 0.012 pooled = 1.2% of Brier. That's the theoretical calibration ceiling.
- Every fixed-effect Platt/bin-lift correction has been trying to shave a signal smaller than the halves-drift noise. That's why they all HOLD.
- 24-47h BSS > 0-5h BSS is counterintuitive — probably long-lead hedges toward base rate (lower Brier "for free"), or captures big-signal patterns (frontal passages) while short-lead has nowcast noise.

## ppbp — pp bias-persistence Stage 0 built + run

Built `analysis/h_pp_bias_persistence_stage0.py` (~200 lines) — sibling of dpbp/wsbp Stage 0. Reads pair log, computes per-regime daily bias, lag-1 autocorrelation. Gates: lag-1 r ≥ 0.35 AND |mean_daily_bias| ≥ 0.10.

**Stage 0 verdict: PROMOTE — 1 regime cleared both gates**:

| Regime | n_days | mean_bias | \|mean\| | lag-1 r | verdict |
|--------|--------|-----------|---------|---------|---------|
| **frontal** | 18 | **−0.106** | **0.106** | **+0.434** | PROMOTE ★ |
| nw_flow | 22 | −0.052 | 0.052 | +0.656 | persistent-but-small |
| others | — | — | — | — | skip |

**Frontal is the winner** — same regime where fixed-effect Platt found signal that then failed. Two different mechanisms converge on frontal as the exploitable subpopulation. **nw_flow** shows strong persistence (r=+0.66) but bias too small under current threshold — revisit if Stage 1 succeeds on frontal alone.

**Caveats**: n=11 lag pairs on frontal is thin; frontal is a rare regime → ppbp would only fire during frontal passages (few per week) → low-frequency correction even if it works.

Next step **not built today**: Stage 1 halves-verify. See `[[project_ppbp_workstream]]`.

## MRMS radar scoping (deferred, not built)

Discussion of what new data could open pp avenues. Ranked recommendation:

1. **MRMS radar (highest impact)** — Multi-Radar Multi-Sensor from NOAA. Free, 2-min cadence, 1km resolution. Would enable actual precipitation nowcasting (0-3h leads where radar crushes NWP). Phased path:
   - Phase 1: radar as ground truth (~2-3 days) — better obs than point stations, sharpens Brier scoring.
   - Phase 2: radar current-state as pp input (~1 week) — 20-40% Brier lift at 0-3h projected.
   - Phase 3: full motion-vector nowcast (~2-3 weeks) — real meteorological nowcast blended with NWP.
2. **NWS QPF** — cheap check first; may already be in the NWS gridpoint API you already call.
3. **Ensemble forecasts (HREF/GEFS)** — proper probabilistic inputs, could retire calibration work entirely. Medium effort.
4. **Longer obs history (NOAA hourly climate normals)** — true climatology, sharpens skill-score comparisons.

Full scope in `[[project_mrms_radar_potential]]`. Not scheduled — decision deferred until pp workstream priority firms up.

## GH Pages deploy issue (unresolved)

Local at v0.6.395d, GitHub Pages stuck showing v0.6.395a. Investigation:
- No `.github/` in repo (per CLAUDE.md GH Actions is dead) — the failing workflow is the auto-generated "pages build and deployment" that GH creates when Pages is enabled.
- Screenshot showed: #3095 succeeded 7:38 AM (probably v0.6.395), #3096 FAILED at 12:22 PM after 17-min runtime (typical Pages build is under 2 min), #3097 stuck "in progress" for 48+ min, UI unresponsive.
- No Liquid tokens in HTML files (grep -c "{{" = 0, "{%" = 0) — not a Jekyll parsing issue.
- Best diagnosis: GitHub Pages infrastructure hiccup, not repo content.
- Created `.nojekyll` file locally (not committed) — would skip Jekyll processing entirely on future deploys. Preventive, not diagnostic.
- **Decision: wait for GH Pages to recover.** Pushing more commits queues behind the stuck ones; won't help. If not resolved in 1-2 hours, push `.nojekyll` as preventive.

## Process lessons

- **`[[feedback_search_before_proposing]]`** — new. Should search codebase for existing metrics before proposing to build one.
- **Menu-and-ambiguous-yes pattern**: violated `[[feedback_no_choice_menus]]` several times ("scope ppbp or stop here — yes?"). User pointed it out; corrected mid-session but the reflex is still there.
- **Diagnosis discipline**: proposed Jekyll as cause of Pages failure with weak reasoning; user pushed back correctly ("doesn't make sense"); retracted. Should hold hypotheses more loosely when evidence is thin.

## Non-actions (checked, no code change)

- **wsbp**: calm regime finally appearing in shadow log (n=25 in 48h state, up from 0 on 08-04) but only n=12 in the 24h antecedent window — MIN_N_ANTECEDENT=20 still not met. Predict one more calm overnight clears it. Preflight `[[preflight_wsbp]]` updated.
- **h L2 τ-suspect**: digest layer-shape sentry reports "all applied layers clean at all bands"; pair-log anomaly h ΔMAE −29.2%. Watch closes clean 08-07.
- **dpbp**: day 2/14 post-flip watch (LIVE since 08-04 v0.6.391). No triggers.
- **Lsb**: day 1/14 post-flip watch (LIVE since 08-05 v0.6.394). Hour 13 SKIP still applied (primary watch point); halves B +4% (secondary).

## Process points

- Committed only the 2 intentional-ship curated JSONs (`c1_confidence_curated.json` + `c1_confidence_curated_v2.json`), left 20 other daily-Fitter-drift curated JSONs uncommitted per `[[feedback_curated_json_daily_drift]]`.
- Version bump correctly used letter suffix for debug-only sweep per `[[feedback_version_bump_convention]]`.
