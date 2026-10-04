---
name: pp-recalibration-session
description: "2026-07-27 PM session on pp recalibration. Three corrective halves tests scaffolded (bin-lift, Platt, two-component Kalman-Platt) — ALL HOLD. Root diagnosis: pp Brier dominated by Uncertainty + Resolution, not Reliability; recalibration ceiling ~5% while halves-inconsistency in level burns more. Evening 07-27 v0.6.382q: h_pp_source_blend.py Stage 0 also HOLD — HRRR and GFS pp near-collinear at 0-48h horizon. Provisional stance: pp = L1-only is the physics floor absent new signal. **2026-08-06 UPDATE:** the one bright spot — h_pp_frontal_platt_stage1 SHIP at frontal × 6-11h from 07-27 evening — has flipped to HOLD on today's re-cut. |Δa| went 0.20 → 1.15 (5.75× worse), one halves direction went pct=-28.56 → +165.82 (sign flip + blow-up), n dropped 292 → 226. Also h_pp_platt_by_regime HOLD (nw_flow + sw_flow coefficients numerically unstable in the thousands). h_pp_bin_calibration flipped MARGINAL → HOLD same day. NO shipping-ready pp correction currently exists. pp is L1-only in production and Stage 1 candidates are all HOLDing."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0ee657df-54d0-435a-bbf2-1a02cf3244b5
  modified: 2026-08-06T17:33:44.136Z
---

# pp recalibration — 2026-07-27 session (v0.6.382j → l PM; v0.6.382q evening source-blend)

## What ran and what came back

Three Stage 0 corrective halves tests scaffolded and executed:

| Script | Method | Verdict |
|---|---|---|
| `h_pp_bin_calibration.py` | Per-decile lift table fit on half A → apply to half B | **HOLD**: Fit A→B +6.46%, Fit B→A +0.87% (both WORSE); 8/10 bin-signs agree but magnitudes unstable |
| `h_pp_platt_calibration.py` | 2-param Newton `σ(a + b·logit(p))` | **HOLD**: Fit A→B +6.56%, Fit B→A +10.45%; **slope b stable (0.628 vs 0.569, \|Δb\|=0.06)**, intercept a drifts wildly (+0.11 vs −0.82) |
| `h_pp_kalman_recalibrate.py` | Fixed b + rolling-window a_t, swept 24h/72h/168h | **HOLD** at all three windows. Best (168h): Fit A→B +7.27%, Fit B→A +9.89%. Confirms b-stability finding but level-recalibration still hurts held-out Brier |

All three scripts: GCS-published, digest-runnable, verdict lines wired for
`build_executive_summary.py`. Also shipped:
- `pp_brier_reliability.py` rewired with proper `VERDICT:` line and GCS
  upload; retracted "rendering bug" section removed.
- Debug page collapsible under per-field snapshot (`renderPpBrierReliability`)
  fetches both reliability + bin-cal JSONs, color-codes gaps.

## Why they all failed — the actual read

Look at the Brier decomposition from `pp_brier_reliability.py`:

- L1 Brier ≈ 0.086
- Reliability component ≈ 0.005 (~5% of total)
- Uncertainty (base rate × 1−base rate) + Resolution dominate

**The calibration gap only accounts for ~5% of total Brier.** Even a
*perfect* recalibration could only reduce Brier by that ~5%, and the
halves-inconsistency in the LEVEL burns more than that per attempt.
Bin 30-40 looks catastrophic (35% → 62% gap) but it's n=1,422 out of
145k — a small tail wagging a huge dog in Brier terms.

Meanwhile the base rate itself is non-stationary within a 30-day
retention window: half A raw Brier = 0.103 (wetter), half B raw
Brier = 0.031 (drier). Any pooled recalibration fit on one gets
punished when applied to the other.

**Three attempts, three HOLDs, one consistent diagnosis: pp Brier is
dominated by irreducible uncertainty and by resolution, not by
miscalibration. Pooled recalibration in any form is chasing the small
component.**

## Slope-stability finding stands

The **shape** of raw HRRR pp miscalibration (Platt slope b ≈ 0.60) IS
a stationary invariant across halves — this was the diagnostic
breakthrough. It just doesn't help ship a correction because the level
non-stationarity swamps it.

If a future session revisits Reliability-attack candidates, use b=0.60
as a fixed prior (no need to re-fit) and focus the design on making
the intercept robust to base-rate shifts. Regime-conditional fits (per
`state_fc`) are the natural next attempt because within-regime base
rate is more stable.

## Booked for fresh session

**Primary candidate: `h_pp_source_blend.py`** — halves-test HRRR +
Pirate Weather + GFS pp weighted average (and/or logistic blend).
**This attacks the Resolution term, not the Reliability term.**
Resolution is a much larger Brier component (~15-25% of total) so the
attackable surface is 3-5× bigger. And it's a genuinely different
mechanism than anything tried today.

All three sources already fetched by the collector — no new
instrumentation. Data already in the pipeline.

Ship gate: same as today's scripts — both halves improve Brier ≥5% AND
blend weights within stability threshold across halves.

**Secondary (if blend also fails): `h_pp_regime_bin_cal.py`** —
regime-conditional bin-lift, fit per `state_fc` so within-regime base
rate is stable. Chases the small (~5%) Reliability component; may only
squeak past the ship gate.

**Accept-L1 branch (if both fail):** stop trying. Document pp as
"at the physics floor for single-lead recalibration on 30-day windows;
Brier gain from further recalibration bounded by ~5%." Wire the
Resolution / Reliability decomposition as a standing debug-page metric
so future changes to raw HRRR or the pair log show up in the numbers.

## Files touched 2026-07-27

- `analysis/pp_brier_reliability.py` (rewired verdict + GCS upload)
- `analysis/h_pp_bin_calibration.py` (new, HOLD)
- `analysis/h_pp_platt_calibration.py` (new, HOLD)
- `analysis/h_pp_kalman_recalibrate.py` (new, HOLD; per-hour refit + subsampling
  for compute — naive per-row version was O(N × W × iters) and hung on 168h window)
- `corrections_debug.html` (new collapsible under per-field snapshot;
  fetch + renderPpBrierReliability with color-coded gap table + halves-verdict
  card)

## Evening 07-27 v0.6.382q — source-blend Stage 0 HOLD

Ran `analysis/h_pp_source_blend.py` (booked as "primary candidate" above).

**Data**: 23,232 pair-log pp rows joined with `gfs_l1_log.json` on (run_hour, valid_time), spanning 07-13 → 07-27 (14-day GFS log retention window). 119,558 pair-log pp rows outside the GFS-log window unjoined. Pirate pp NOT tested — Pirate is fetched live per tick but never logged historically (no rolling file). Would need a `pirate_l1_log.json` ship first.

**Weighted blend** (α · HRRR + (1−α) · GFS):
- Half A: α = 0.8915  |  Half B: α = 1.0000  |  |Δα| = 0.1085
- Brier Δ: A→B = +0.00%, B→A = −0.00%
- **HOLD**: GFS non-informative given HRRR. Either α is roughly 1.0 (pure HRRR) or GFS ≈ HRRR (blend collapses to identity).

**Logistic blend** σ(a + b_H · logit(H) + b_G · logit(G)):
- First pass: Newton diverged (b_H → −8e10) — same collinearity trap as PM's Kalman-Newton hang per HANDOFF.
- Second pass with ridge damping (λ = 1e-3 · n on Hessian diagonal): half A a=−15.26, b_H=−0.71, b_G=−1.01, log-loss=0.08 (well-conditioned); half B still hit a flat region (b_H = +4515) with ridge — sparse-positives problem.
- Brier Δ: A→B = −2.94% (marginal, one-sided), B→A = +45%
- **HOLD**: below the 5% ship gate + halves-asymmetric.

**Physical interpretation**: HRRR and GFS pp are near-collinear at 0-48h horizons — both models post-process from the same NCEP soup and share recent-obs assimilation. The Resolution term attack requires a source that's actually **independent** — Pirate weather (from IBM's model) would be a better third leg but needs historical logging first.

**Provisional stance**: pp = L1-only is the physics floor absent new signal. Do NOT re-run bin-lift / Platt / Kalman variants (per HANDOFF). Do NOT re-run source-blend without Pirate. Next attempts require either:
1. Ship `pirate_l1_log.json` (per-tick), wait 14 days, re-run source-blend at 3 sources.
2. Regime-conditional recalibration (fit within-regime; base rate is more stable per-regime) — cheapest inside the existing scripts.

## Evening-2 07-27 v0.6.382r — both #1 and #2 executed same session

### #1 — pirate_l1_log SHIPPED

`weather_collector/processors/pirate_l1_log.py` + `fetchers/pirate_weather.py` (extended to extract `hourly_precip_probability`) + collector wire. 14-day retention on GCS. Data starts accruing next collector tick post-deploy. **Earliest 3-source pp source-blend re-test 2026-08-10** when the log has 14 days of coverage. Follow-up: extend `h_pp_source_blend.py` join to include pirate_l1_log entries; add a 3-feature logistic variant (a + b_H·logit(H) + b_G·logit(G) + b_P·logit(P)) with ridge.

### #2 — `h_pp_platt_by_regime.py` Stage 0 → HOLD overall, frontal MARGINAL_DRIFT

Same session, same night. Verdict aggregate: **HOLD** (weighted-by-n +21.08% / +25.15% — worse). BUT per-regime table showed a strong sub-signal:

| Regime | n | pctA→B | pctB→A | verdict |
|---|---|---|---|---|
| calm | 6,051 | −1.59% | +2.77% | HOLD (b=2726 numerical explode — zero rainy hours in one half) |
| **frontal** | **2,255** | **−15.49%** | **−15.60%** | **MARGINAL_DRIFT** (|Δa|=0.66 > 0.5 gate; |Δb|=0.21) |
| ne_flow | 14,913 | +72.47% | +85.33% | HOLD |
| nw_flow | 18,849 | +48.21% | +100.27% | HOLD |
| pre_frontal | 20,707 | +15.27% | +16.79% | HOLD |
| se_flow | 30,105 | +4.60% | −2.41% | HOLD |
| sea_breeze | 6,448 | +17.84% | +6.56% | HOLD |
| sw_flow | 40,632 | +10.73% | +1.43% | HOLD |

**Key read**: pooled non-stationarity that killed the earlier Platt / bin-lift / Kalman attempts was NOT base-rate non-stationarity within a homogeneous population — it was **different miscalibration signs across regimes canceling out at the pooled level**. Recalibration in ne_flow makes things dramatically WORSE (+72% Brier) because ne_flow raw pp is already well-calibrated (or over-calibrated) — Platt shifts it in the wrong direction. Frontal raw pp is systematically under-forecasting rain during frontal passages, so Platt corrects in the right direction with large magnitude.

**Design seed** — frontal-only pp recalibration (`fronal_pp_recalibration.py` Stage 1 next): fit Platt only on state_fc.regime='frontal'; apply at runtime only when state_fc.regime='frontal'. Would need a new specialist on the persistence_gate_base template (or similar). Halves-MARGINAL_DRIFT is not SHIP — need a Stage 1 with either (a) stricter windows to close the |Δa|=0.66 drift, (b) accept as MARGIN and see how it performs live, or (c) different fit form (e.g., linear-in-p rather than logistic to reduce param count). Frontal-only base rate is much more stable than pooled — that's why halves converge better here.

**Ridge-damping-doesn't-catch-class-imbalance**: calm had 6,051 rows but essentially zero rain events in one half — Newton flew off to b→+2726 (the "steepest slope" solution when logistic tries to separate a class boundary from no positives). The RIDGE=1e-3·n term should have caught this but didn't because with zero positives the gradient scales differently. Future scripts should add a minimum-positive-count check per regime (e.g. skip if either half has < 20 positives).

## Evening-3 07-27 v0.6.382s — Frontal-only Stage 1 → SHIP at 6-11h with fixed b=0.6

Followed the "design seed" from the Stage 0 evening-2 finding. Built `analysis/h_pp_frontal_platt_stage1.py` — four halves-refit variants inside the frontal-only population:

1. **Pooled free** — reproduces Stage 0: MARGINAL_DRIFT (−15.21% / −15.19%, |Δa|=0.68).
2. **Pooled fixed b=0.6** — closes the drift: MARGINAL_STABLE (−7.90% / −4.99%, |Δa|=0.21). One half just under 5% ship gate.
3. **Per-band free** — all HOLD; short-lead bands (n≤587, 10% positive-rate) blow up numerically (Newton pathology on class-imbalance).
4. **Per-band fixed b=0.6** — one band **SHIPS**: **band 6-11h, Brier lift −28.56% / −18.73%, |Δa|=0.20**, n=292.

**Design that Stage 3 would wire**:
- Apply `σ(a_t + 0.6·logit(raw_p))` only when `state_fc.regime_synoptic == "frontal" AND lead_h ∈ [6, 11]`
- Refit `a_t` on a rolling 30-day frontal-6-11h window (Fitter cadence)
- Everywhere else: pp stays raw HRRR L1

This is the first shippable pp correction found in weeks of investigation. Ceiling identified in the pooled Stage 0 evening-1 session (~5% Reliability) doesn't apply within frontal-6-11h because that subpopulation has a fundamentally different (and more consistently under-forecasting) calibration than pooled.

**Stage 2 next** — build `h_pp_frontal_6_11_platt_stage2.py` that measures the calibrated Brier via walk-forward evaluation (fit on days 1-N, score on day N+1, roll forward) rather than 50/50 halves. If walk-forward confirms −15% to −30% Brier lift, Stage 3 wire is safe. If it doesn't, halves-SHIP was window-lucky. Book for a fresh session (want at least 3-5 more days of frontal passages first — n=292 is tight for walk-forward).

**Number of positives**: frontal pp has 10.1% positive rate (rain events) across the 30-day window; the 6-11h band with n=292 has ~29 positive rows. Halves-fit A gets ~14-15 positives, half B gets the other half. Small-sample. Watch for over-fit.

Also flagged: other bands (0-5h, 12-23h, 24-47h) can't be fit cleanly — Newton diverges on the class-imbalance + limited-features. Future h_pp_* scripts should include a min-positive-count sanity check.

## Related

- [[project_pp_brier_reliability]] — 07-21 scaffold + retraction that set up today's work
- [[feedback_measure_against_live_stack_baseline]] — same pattern class
- Failure class of L3-for-pp (07-04 drop) is the same mechanism as
  today's HOLDs: signal in aggregate, doesn't transfer out-of-sample

## 2026-08-06 re-check

Ten days after the 07-27 SHIP, `h_pp_frontal_platt_stage1` band_6-11_fix flipped:

| Metric | 07-27 (SHIP) | 08-06 (HOLD) |
|---|---|---|
| n | 292 | 226 |
| \|Δa\| | 0.20 | 1.15 |
| pct A→B | −28.56% | +165.82% |
| pct B→A | −18.73% | +5.27% |

Sign flip and blow-up in the A→B direction; n *dropped* rather than accumulating more frontal passages. Same-day: `h_pp_platt_by_regime` HOLD (nw_flow + sw_flow coefficients numerically unstable in the thousands — Newton diverging on class-imbalance as flagged 07-27); `h_pp_bin_calibration` flipped MARGINAL → HOLD.

**Class of failure**: the same "signal in aggregate, doesn't transfer out-of-sample" pattern the 07-27 file already documented. 292 was tight for walk-forward; 226 is worse. Stage 2 walk-forward should NOT run against the current data — it will just codify the halves-flip.

**Current stance**: pp is L1-only in production AND has no Stage 1 candidate holding. Whole `[[project_pp_brier_reliability]]` calibration-correction workstream is dormant. Debug page pp cell shipped v0.6.395b showing raw Brier value (`660.48 Brier (L1 only)` for 7d, `5.85 Brier (L1 only)` for 24h) — auto-flips to `(Δ−X.XX)` if any pp correction ever wires. Zero maintenance on flip.

Next legitimate re-check: after ≥5 fresh frontal passages accumulate (frontal 6-11h needs positive-rate rows to stabilize). Don't re-run before then.

## 2026-08-06 addendum — BSS + ppbp Stage 0

Ran `pp_brier_decomposition.py` (which already computes BSS vs climatology per band — see `[[feedback_search_before_proposing]]`):

| Band | n | BSS | Reliability | Resolution | Uncertainty |
|------|---|-----|-------------|------------|-------------|
| 0-5h | 10,421 | +36.2% | 0.019 | 0.058 | 0.111 |
| 6-11h | 11,634 | +35.5% | 0.018 | 0.057 | 0.110 |
| 12-23h | 23,268 | +45.6% | 0.016 | 0.066 | 0.110 |
| 24-47h | 46,536 | +46.2% | 0.011 | 0.062 | 0.110 |
| Pooled | 91,859 | +43.5% | 0.012 | 0.060 | 0.110 |

**Interpretation**: pp raw signal is REAL (+36-46% BSS). But calibration budget is tiny — Reliability = 0.012 pooled = 1.2% of Brier is the theoretical ceiling for any calibration correction. That's why every fixed-effect approach HOLDs: signal < halves noise. Antecedent-error (ppbp) is the correction type most likely to fit inside that budget.

**ppbp Stage 0 built + PROMOTE for frontal** — see `[[project_ppbp_workstream]]`. Same regime `h_pp_frontal_platt_stage1` identified but with different mechanism. Two independent analyses converge on frontal.

**Radar as fundamentally different avenue** — see `[[project_mrms_radar_potential]]`. Would change pp INPUT signal (MRMS gives real precip data) rather than trying to correct the current one. Deferred pending pp workstream priority decision.
