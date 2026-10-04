---
name: project-raw-difficulty-index
description: "2026-08-04 v0.6.392. Per-field ratio of trailing-7d raw MAE ÷ trailing-90d reference raw MAE (7d excluded from reference). Answers \"did the model improve, or was the weather easier?\" — the confounding question observed lift alone cannot resolve. Reported in the debug page audit label. Standardized-lift phases 2-4 deferred."
metadata: 
  node_type: memory
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-04T14:55:37.104Z
---

# Raw-difficulty index

## What it is

Per-field scalar: `raw_mae_7d / raw_mae_ref` where `raw_mae_ref` = n-weighted raw MAE over the trailing 90 calendar days, excluding the 7d itself from the reference.

- **Ratio > 1.0** = raw model itself struggled more than usual this week (weather harder for the raw model)
- **Ratio < 1.0** = raw model had it easier than usual
- **Ratio ≈ 1.0** = normal week

Per-field normalization prevents unit mixing (can't average °F with W/m²).

## Where it lives

- **Emit:** `analysis/mae_over_time.py` → `raw_difficulty_index` block in `mae_over_time.json`. Contains per-field ratios + unweighted mean across fields + reference-window metadata.
- **Display:** debug page audit label under the per-field snapshot section. Shows mean + top-3 hardest + top-3 easiest.

## What it answers

Joe's question from external review: "did the model improve, or was the weather easier?"

Weekly aggregate correction lift can move because (a) the correction got better, (b) the weather got easier for the raw model. Persistence skill can't disambiguate because persistence difficulty is itself weather-dependent (stable ridges → easy for persistence, fronts → hard). Raw MAE is a correction-independent difficulty reference; that's the key.

Framework Joe outlined: three lines together — observed lift, standardized lift, raw-difficulty index. Only the third line (raw-difficulty index) shipped v0.6.392. Standardized-lift Phases 2-4 deferred as they don't unlock decisions the per-cell (regime × band) reads don't already answer.

## First-run finding (08-04)

Mean 1.04× (flat) hides bimodal spread — this week was cloudy-and-mild:
- **Cloud fields harder than 90d normal:** pa 1.67×, cm 1.62×, pp 1.29×, pr 1.20×, ch 1.19×, cl 1.18×
- **Thermo fields easier than 90d normal:** dp 0.57×, h 0.62×, wd 0.66×, t 0.77×
- **Middle:** sr 1.08×, wg 1.06×, ws 0.90×, cc 0.84×

Interpretation: aggregate mean says "normal week" but the field distribution tells a real story. Explains a lot of the recent per-field variance we've been chasing.

## Design notes

- Reference is trailing 90 days, 7d excluded from the reference (so numerator and denominator are disjoint).
- MIN_N floor inherits from `mae_over_time`'s per-day series — no separate floor.
- Falls silent (no emit) if <7d of history is available.
- Mean is UNWEIGHTED across fields — treats each field as equally important. Alternative would be n-weighted but that would let ch (large pair volume) dominate.

## What NOT to do with it (per `[[feedback_audit_label_direction_neutral]]`)

The audit label DOES NOT prescribe a direction ("discount weekly lift" is wrong for the >1.0 case — fixed-effect corrections show smaller % on hard weeks; direction depends on correction shape). It names the confound and lets the reader interpret.

Current label wording: "Values >1 indicate the underlying weather was harder for the raw model than usual; interpret weekly correction gains in that context."

## What's NOT done (deferred)

- **Phase 2 (standardized-lift emit):** compute `sum(w_d^ref * (mae_prod_d - mae_raw_d))` with weights fixed to the 90d reference distribution. Not shipped.
- **Phase 3 (three-line display):** observed lift + standardized lift + difficulty ratio side-by-side per field on the debug page. Not shipped.
- **Phase 4 (multi-dim difficulty score):** extend beyond raw MAE — inter-model disagreement (`cloud_inter_source_sigma` already in pair log), observed volatility, regime × lead-band. Not shipped.

Revisit if a specific decision gets fooled by weather-mix (evidence Phases 2-3 were actually needed).

## Related

- `[[project_metric_provenance_v0391]]`
- `[[feedback_audit_label_direction_neutral]]`
- `[[feedback_measure_before_concluding]]`
- `[[project_08_04_session]]`
