"""Stage 0 — Regime-transition correction-OFF gate.

Hypothesis: correction layers systematically hurt during regime transitions.
Meta-finding from 2026-08-17 closures across six sr-side workstreams (8a, 8b,
cm Lc wet, cl h-predictor, Lc EMA/Kalman, Lc gate-rule): every "recent obs
predicts near future" architecture failed in fast-moving regimes for the same
reason. Extrapolation: the failure isn't specific to sr — it applies to any
layer that assumes stationarity within the correction window.

Test: for each live specialist (chp, wdp, Ccd, Lc, Lsr, Lsb, dpbp, pr L2 gate),
partition pair-log rows by transition state (C1a) and compare the layer's
help-rate on stable vs transition rows. If several layers show materially
worse help (or negative help) on transition rows, the ship shape is:

  Wrap live specialists in a `transition_gate`: if state_fc.regime !=
  state_obs.regime, skip layer application for the LAYERS FLAGGED. Route
  is transition-aware but not per-layer-specific — one axis, many gates.

Stage 0 gate (this script should implement, not yet):
  1. Load pair log with applied_layer stamps + state_fc/state_obs regimes.
  2. For each (layer, field, band), compute:
       n_stable, help_stable_pct     = MAE improvement on stable rows
       n_trans, help_trans_pct       = MAE improvement on transition rows
       Δhelp_pp                       = help_stable − help_trans
  3. Rank layers by Δhelp_pp. Report the top losers.
  4. Verdict: PROMOTE (build gate) if ≥3 live layers show Δhelp_pp ≥ +10pp
     AND halves-stable AND transition-row n ≥ 200 in each.

Blockers before Stage 1:
  • Definition of "transition" — C1a fires on state_fc != state_obs but that's
    the OBSERVED transition. For a forecast-issue-time gate, need transition
    signal available at run_time, not obs_time. Options: (a) same-run C1a
    proxy (regime_fc at lead=0 vs lead=6), (b) recent-obs-based (regime_obs
    over the last 3h), (c) forecast-only cross-run spread.
  • Attribution: negative help on transitions could be that transitions
    themselves are hard (regardless of layer). Need to check raw MAE on
    transition rows vs stable — if raw MAE is already 2× on transitions,
    the "layer hurts on transitions" reading could be "layer helps less
    because there's less to help." Ratio (layer help / raw MAE) is the
    right normalization.

References:
  • analysis/regime_transition_audit.py — descriptive stats on transitions.
  • project_hypothesis_backlog — sr closure notes for the meta-finding.
  • [[feedback_regime_gate_first]].
"""

VERDICT = "STAGE 0 SCAFFOLDING — regime-transition correction-OFF gate mechanism-test pending. See docstring for spec. Testable against pair log's applied_layer + state_fc/state_obs stamps once implemented."
print(VERDICT)
