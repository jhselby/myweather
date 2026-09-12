"""Stage 0 — sr regime-conditional Lsr refit.

Hypothesis: sr has a large across-regime spread (state_stratified_accuracy
today: 154.83-unit MAE spread across synoptic bins — the top signal in that
diagnostic). Current Lsr is pooled across regimes with a narrow sea-breeze
override (Lsb) but no first-class regime split. Regime-conditional Lsr fit
should capture the between-regime variance.

Test: fit an additive Lsr correction per (synoptic_regime, lead_band) instead
of pooled+narrow-override. Compare pooled Lsr, regime-Lsr, and pooled+Lsb
(live shape) on held-out.

Ship shape (if it clears):
  Replace solar_correction.SR_BIAS_BY_REGIME dict (currently a single-lead
  additive) with a (regime, band) table analogous to L3/L4. Preserve Lsb
  as a further sea-breeze-specific override on top.

Stage 0 gate (this script should implement, not yet):
  1. Load pair log filtered to sr rows with state_fc.regime_synoptic + err_l1.
  2. Fit additive bias per (regime, band) on train half (chronological).
  3. Score on held-out half. Compare MAE(pooled Lsr) vs MAE(regime Lsr).
  4. Verdict: PROMOTE if regime-Lsr beats pooled Lsr by ≥5% held-out AND
     ≥4 (regime, band) cells have n ≥ 200 AND halves-stable.

Blockers before Stage 1:
  • Overlap with L2_NBM (sr routes NBM at leads ≥6 for most regimes in the
    30d fit). If NBM sr is winning, this correction sits inside the HRRR
    path — measure the marginal L1-source-mix impact.
  • Interaction with Lsb (sea_breeze narrow override). Either the new
    (sea_breeze, band) cells subsume Lsb entirely, or Lsb wins on the
    cc<25 sub-slice; that decision needs to be made pre-Stage 1.
  • cc-miss confound (Cause A from sr_shortwave_cc_confound). If today's
    confound audit says the sr regression is cc-driven, refitting sr Lsr
    is fixing the symptom. Read that audit's verdict before building.

References:
  • analysis/state_stratified_accuracy.py — today's 154.83 spread finding.
  • analysis/sr_shortwave_cc_confound.py — Cause A vs Cause B diagnostic.
  • weather_collector/processors/solar_correction.py — current Lsr.
  • project_lsr_recent_bias_gate — the existing recency-bias sibling gate.
"""

VERDICT = "STAGE 0 SCAFFOLDING — sr regime-conditional Lsr refit mechanism-test pending. See docstring for spec. Motivated by today's state_stratified_accuracy sr×synoptic spread of 154.83 W/m² across bins."
print(VERDICT)
