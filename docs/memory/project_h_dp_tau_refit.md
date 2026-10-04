---
name: h-dp-tau-refit
description: "SUPERSEDED 2026-08-07 by v0.6.390g soft_ramp retune ([[project_h_l2_shape_retune]]). h uses soft_ramp not exp(-lead/τ); dp is Magnus-derived. Script emits VERDICT: KILL as supersession guard (08-12 v0.6.401i) so future STAGE 0 PROMOTE reads don't propose reverting the closed-clean shape retune."
metadata:
  node_type: memory
  type: project
  originSessionId: ee3022f3-1d0e-4e93-abfb-dbc558df1928
  modified: 2026-08-12T14:33:47.287Z
---

# 08-12 UPDATE (supersession guard shipped)

Today's digest showed `h_h_dp_tau_refit` STAGE 0 PROMOTE h→τ=24 (+4.6%), dp→τ=24 (+3.3%) — flipping back on despite [[project_h_l2_shape_retune]] having landed 08-07. Investigated: the τ-decay mechanism this script tests is NOT what h/dp use in production. h uses `_soft_ramp_factors(lead)` piecewise-linear (H_SOFT_RAMP_FLOOR=0.1, H_SOFT_RAMP_END=10) per `weather_collector/processors/corrected_hourly.py:179`. dp is Magnus-derived from t + h — no direct L2 bias to tune τ for. Adopting the STAGE 0 PROMOTE would revert the CLOSED-CLEAN shape retune.

**Guard shipped**: `analysis/h_h_dp_tau_refit.py` summary now emits `VERDICT: KILL (supersession guard) — ...` when per-field PROMOTE would fire. Per-field lines retain the PROMOTE text (still useful for the sentry pattern), but the summary verdict — the one the digest reads — is KILL. Docstring rewritten to lead with the supersession context.

**How to apply on future flips of this script:** verdict is now KILL. If the digest ever shows this script's verdict change back to PROMOTE, that means someone edited the guard out — investigate whether the mechanism swap is genuinely being reconsidered.

---

# h + dp τ refit — pending Stage 0

**Trigger:** Joe asked "what's happened to h, is it L2 tau" on 2026-07-30 afternoon after h showed +7% Prod-vs-Raw on the scoreboard trailing card. Diagnostic pulled from time_series_diagnostic.json:

- **h/production** — helps 0-5h (−18%), hurts 6-11h (+13%), 12-23h (+13%), 24-47h (+11%). Clean crossover between lead 5 and lead 6.
- **dp/production** — helps 0-5h (−28%), hurts 6-11h (+7%), 12-23h (+8%). Same signature, less severe.

Both surfaced automatically by the layer-shape sentry same day (v0.6.390d). h is the acute one (worst pooled hurt). dp is quieter but present.

## Interpretation

Classic "decay time-constant too long" signature. L2 additive bias is REAL at short lead (station bias predicts model error) but the fitter keeps that bias alive too far into the forecast horizon. If the bias signal decays in reality within ~6 hours but τ says "decay over 24h", L2 imports stale bias at long lead.

Distributional alternative rejected: if it were "raw got accurate, L2 now noise," L2 would hurt uniformly at all leads. The clean crossover at lead 5→6 rules out distributional over-correction.

## Not a same-day fix

Refit needs its own workstream:

1. **Stage 0:** sweep candidate τ values (e.g., {4, 6, 8, 12, 16, 20, 24}) via a fork of `decay_tau_tuning.py` restricted to h and dp. Score each on held-out pooled MAE + per-band. Simplest gate: pick τ that maximizes pooled MAE improvement WITHOUT making any lead-band worse than raw.
2. **Stage 1:** halves-stability check on winning τ.
3. **Stage 2:** walk-forward held-out.
4. **Stage 3:** ship τ change with 7-day gate.

Alternative to full refit — surgical: add lead-band SKIP for h/L2 and dp/L2 at 6-11h+ leads. Simpler, less invasive, but doesn't recover the actual signal that L2 has at those leads with the right τ.

## Not on any watch

Neither field is on the active-14-day-watch list. Layer-shape sentry now covers them going forward. Add proper watch entries when Stage 3 ships.

## Related

- [[project_layer_shape_sentry]] — the instrument that surfaced this
- [[project_lc_regime_conditional]] — same week's shift-table-broke pattern, different failure mode
- `decay_tau_tuning.py` — canonical τ-tuning script (this refit would fork it)
