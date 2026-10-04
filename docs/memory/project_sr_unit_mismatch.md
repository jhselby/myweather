---
name: sr-unit-mismatch
description: "Model direct_radiation is direct-beam only; Tempest solar_radiation_wm2 is total shortwave. 07-07 first read: nw_flow benefits from unit fix (−55% MAE); pre_frontal/sea_breeze worse. 07-11 confound diagnostic first real read: **sea_breeze shows Cause B evidence** (+83.6 W/m² matched-bin bias — Open-Meteo over-forecasts total shortwave even when clouds are right); **pre_frontal ambiguous** (+14 matched, +63 small-miss, +3 big/severe — noisy, deferred). Fix chain remains regime-conditional not global. Blocks any sr-metric ship (l2_lead_decay_fit, l2_regime_lead_analysis, sr_sea_breeze_lsr_refit) — their verdict strings will churn until the unit gap is resolved. Next step: write sea_breeze-conditional Lsr refit as Stage 1 candidate."
metadata:
  node_type: memory
  type: project
  originSessionId: 6bb3eadf-bcbe-4bab-ba53-c02b00010f53
  modified: 2026-08-12T14:05:06.211Z
---

# 08-12 UPDATE (batch-close sr-side verdict flips)

Digest flagged three sr-side flips today, all downstream of this blocker — no action on any:

- **`l2_lead_decay_fit`: IMPLEMENT L2 LEAD-DECAY → KEEP L2 FLAT.** Only sr was clearing the +2% gate; today sr slipped below. sr's L2 measurement folds in the direct-vs-shortwave gap → the "gain" isn't station consensus signal. Do-not-ship regardless of verdict text.
- **`l2_regime_lead_analysis`: SKIP-TABLE CANDIDATE → CLEAN.** sr τ=120h now wins/flat in every judgeable cell. Script's own verdict already carries the `⚠ DO NOT SHIP — blocked by unit mismatch` guard pointing here. Movement is unit-gap noise.
- **`sr_sea_breeze_lsr_refit_stage1`: PROMOTE → MARGINAL.** Halves went from 2/2 confirming to 1/2. Same substrate — the "bias" being fit is direct-vs-shortwave gap on the fired subset, not a genuine sea-breeze physical bias. Cause B confound (2026-07-11 read) is exactly what would produce this pattern.

**How to apply on future sr-metric flips:** if the script measures `|obs − forecast_direct|` (Tempest total vs Open-Meteo direct-beam), the verdict is unit-contaminated regardless of magnitude. Do not open an investigation. Escalate only if a script is refactored to use `forecast_shortwave` (Open-Meteo total) and still shows movement — that would be real cause-B signal.

**What would unblock these three:** ship the sea_breeze-conditional Lsr refit against `forecast_shortwave` (still open per the "Next step" line above). Once Lsr is measured against the correct model channel, downstream L2 / regime-lead / Lsb refit numbers become interpretable.

---


## Discovery (2026-07-06)

Investigation into "sr τ=24h L2 lead-decay" ship candidate exposed a unit mismatch masquerading as a station bias: model `direct_radiation` (Open-Meteo) is direct-beam only, but Tempest station `solar_radiation_wm2` measures total shortwave (direct + diffuse). A tick showed 18/19 Tempest stations reporting sr at 96–165 W/m² while model direct_radiation[0] = 4 W/m². The gap has been contaminating Lsr — its per-regime bias magnitudes (−60 to −110 W/m²) were fitting the direct-vs-total unit gap on top of any real regime signal.

## Fix chain

**v0.6.308 (2026-07-06):** Fetch `shortwave_radiation` + `diffuse_radiation` from Open-Meteo alongside `direct_radiation`.

**v0.6.309 (2026-07-06):** Shadow-log model shortwave + diffuse on every sr pair row. `forecast_shortwave` and `forecast_diffuse` stamped alongside existing `forecast_l1`.

**Analysis:**
- `analysis/sr_shortwave_bias.py` (2026-07-06): compares `|obs − forecast_direct|` vs `|obs − forecast_shortwave|` per regime.
- `analysis/sr_shortwave_cc_confound.py` (2026-07-07): joins each sr shadow-log row to paired cc row at same (run_time, valid_time), stratifies sr signed error by |Δcc| bins to disambiguate Cause A vs Cause B.

## First shadow-log read (2026-07-07, n=1,200 day 1)

**Result did NOT match the "unit fix collapses Lsr's regime bias everywhere" hypothesis.** Direction is regime-specific:

| Regime | \|direct−obs\| | \|sw−obs\| | Δ | direct bias | sw bias | n |
|---|---|---|---|---|---|---|
| nw_flow | 5.96 | 2.66 | −55.4% | −5.96 | −2.46 | 82 |
| pre_frontal | 6.37 | 12.94 | +103% *worse* | −3.14 | +11.84 | 198 |
| sea_breeze | 111 | 168 | +52% *worse* | −100 | +169 | 92 |
| unknown | 275 | 367 | +33% *worse* | −275 | +367 | 21 |
| se_flow | 132 | 131 | −0.7% | −126 | +130 | 167 |
| **OVERALL** | **33.15** | **39.89** | **+20% worse** | −31 | +39 | 1,200 |

**Interpretation:** In nw_flow the unit fix works cleanly. In cloudy/marine regimes (pre_frontal, sea_breeze) the model's `total_shortwave` OVER-forecasts by more than the direct-vs-total gap can explain. Signals a real over-forecast in Open-Meteo's total shortwave in those regimes on top of the definitional gap.

**Two candidate causes for the pre_frontal/sea_breeze overshoot:**
- **Cause A** — Model under-forecasts cc in those regimes (known bias). Its `total_shortwave` mechanically overshoots because it's computing insolation through cleaner skies than reality. Not an sr bug; it's cc error leaking into sr.
- **Cause B** — Real Open-Meteo diffuse/aerosol modeling gap. Even at matched cloud cover, HRRR/GFS may over-predict diffuse component in marine humid airmasses.

## Confound diagnostic first real read (2026-07-11)

`sr_shortwave_cc_confound.py` shipped output for 2 regimes:

**sea_breeze (n=2,017):**
| \|Δcc\| bin | n | mean signed err_sw | MAE_sw |
|---|---|---|---|
| matched (<10) | 825 | **+83.63** | 100.61 |
| small miss (10-25) | 286 | +225.33 | 255.66 |
| big miss (25-50) | 453 | −28.73 | 252.77 |
| severe miss (≥50) | 453 | +101.64 | 197.37 |

→ **Cause B evidence:** matched-bin bias is +83.6 W/m² — model over-forecasts total shortwave in sea_breeze **even when clouds are right**. Justifies a sea_breeze-conditional Lsr refit against shortwave.

**pre_frontal (n=5,064):**
| \|Δcc\| bin | n | mean signed err_sw | MAE_sw |
|---|---|---|---|
| matched (<10) | 2,432 | +14.07 | 49.55 |
| small miss (10-25) | 513 | +63.36 | 82.54 |
| big miss (25-50) | 733 | +3.14 | 70.58 |
| severe miss (≥50) | 1,386 | +3.08 | 68.64 |

→ **Deferred.** Neither pattern fits cleanly — matched +14 is small, small-miss +63 is real but big/severe collapse to ~zero. Accumulate 1-2 more weeks.

**Other 5+ regimes (nw_flow, calm, ne_flow, sw_flow, se_flow, frontal, nor_easter):** not in output — likely n-thresholded out or the script targets only the two problem regimes from the 07-07 read. Verify script behavior next time it runs.

## Status

Fix chain framing shifts from "global unit swap" to **regime-conditional Lsr refit**. Next steps:
1. ~~Stage 1 candidate write-up: sea_breeze-conditional Lsr refit against total shortwave~~ **SHIPPED 2026-07-16** — see below.
2. Weekly re-read of `sr_shortwave_cc_confound.py` to see if pre_frontal signal stabilizes.
3. Verify why nw_flow (memory says benefits from unit fix) doesn't appear in confound output — the diagnostic should cover it too.

## 2026-07-28 update — sr L2 candidate re-surfaced, analysis scripts patched

Digest triage session hit exactly the same trap as 07-06: `l2_lead_decay_fit.py` recommended sr τ=120h (+4.5% MAE held-out), `l2_regime_lead_analysis.py` (running stale τ=24h) proposed a skip table, and `h_full_regime_sweep.py` surfaced 9 sr-L2 ADD candidates. Under investigation:

- Verified sr has **no L2 wired in production**: `station_bias.py` covers only t/h/pr; `corrected_hourly.py` `DEFAULT_L2_TAUS` has t/h/pr only; `direct_radiation_post_l2` array has no writer; pair-log spot check (20k rows) shows `forecast_l2 == forecast_l1` bit-identical for sr.
- Analysis scripts are computing hypothetical station-Kalman lift against `direct_radiation` — but `sr` pair-log obs is `solar_wm2` (total shortwave). Same unit gap as 07-06.
- Re-cut `l2_regime_lead_analysis` at τ=120h confirmed 0 losses (2 WIN, 30 flat) — "clean" verdict is real at the numeric level but the underlying signal is unit-gap contamination.

**Patches landed 2026-07-28 to prevent re-triage next session:**
- `analysis/l2_regime_lead_analysis.py` — TAU_H 24 → 120, docstring rewritten with ⚠ blocker header, verdict emit line now says "⚠ DO NOT SHIP: blocked by unit mismatch."
- `analysis/h_full_regime_sweep.py` — 5-line filter in `emit()` suppresses sr L2 ADD candidates with comment pointing here.

**Do not re-open sr L2 as a candidate** until Lsb (`sr_sea_breeze_lsr_override.py`) shortwave-refit chain resolves. That chain's watch: Stage 1 + Stage 2 both dropped PROMOTE/HOLD → MARGINAL in the 07-28 digest (halves went 2/2 → 1/2 on Stage 1; Stage 2 shows −17.6% regression in 75-100 shortwave-miss lead-band cell). See `sr_sea_breeze_lsr_refit_stage1/2` outputs.

Once shortwave-refit settles, sr L2 becomes wireable but only against **shortwave** forecast (not direct), regime-conditional, with Lsr/Lsb interaction re-thought — not the naive DEFAULT_L2_TAUS extension the analysis scripts were suggesting.

## Stage 1 result — 2026-07-16 (v0.6.353c)

`analysis/sr_sea_breeze_lsr_refit_stage1.py` first read: **PROMOTE**.

- Setup: split sea_breeze sr rows 60/40 by obs date; train fits a per-local-hour signed bias table on `(forecast_shortwave − observed)`; test compares intervention (fc_sw − bias) vs baseline (current Prod post-Lsr on direct_radiation).
- Data: n=3,548 total (2026-07-06 → 2026-07-13), train 2,128 / test 1,420.
- **Held-out: baseline MAE 137.93 → intervention MAE 77.64 (+43.71%).**
- Halves check: A→B +26.55% / B→A +38.58% (2/2 hits).
- Ship gate: PROMOTE (≥5% + halves confirm).
- Overall fit bias +67.60 W/m² matches confound diagnostic +83.6 direction — real overshoot.

**Caveats:**
- Small sample (test n=1,420 spans just 3 days).
- Baseline MAE differs a lot between halves (298 vs 131) — one half has hotter sea_breeze days than the other. Effect is real either way but underlying variance is high.
- Per-hour bias table has only 7 populated hours (12, 14, 15, 16, 17, 18, 19); other daytime hours would use the +67 overall fallback.

**Next:** Stage 2 = full per (regime × hour) cross-cut across ALL regimes (extend to nw_flow, se_flow, pre_frontal etc. once each has similar sample), plus stability check across multiple week windows. If Stage 2 holds, Stage 3 wires a `_BIAS_BY_REGIME_HOUR_SHORTWAVE` fallback that swaps the source signal to shortwave for the regimes where it wins.

Related: [[07-06-session]], [[07-07-session]], [[project-hypothesis-backlog]], [[project-todo]].
