---
name: cc-blend-formula-stage1
description: "cc regime-conditional blend formula pipeline. Stage 0 (h_cc_blend_formula) flagged 5 STABLE ★ non-max regime wins 09-02. Stage 1 halves-verify (h_cc_blend_formula_stage1, v0.6.537) shipped 09-02 with 4 SHIP regimes at day 1/7: frontal/ne_flow/pre_frontal/sea_breeze all prefer random over live max. se_flow demoted SKIP-ccd (Ccd already SKIP_REGIMES it). sw/nw/calm demoted SKIP-mag (halves A negative). Earliest wire ~09-09."
metadata: 
  node_type: memory
  type: project
  originSessionId: e218572d-d5db-4370-b7b7-f278ad0d6f2e
  modified: 2026-09-02T13:04:47.079Z
---

# cc regime-conditional blend formula

## Pipeline state (2026-09-02)

Three-stage promotion pipeline for switching Ccd's cc derivation from pooled `max` to per-regime formula selection:

| Stage | Script | Status |
|---|---|---|
| 0 (pooled signal) | `analysis/h_cc_blend_formula.py` | PROMOTE — 5 STABLE ★ regimes prefer `random` over `max` |
| 1 (halves-verify) | `analysis/h_cc_blend_formula_stage1.py` (v0.6.537) | Day 1/7, 4 SHIP regimes |
| 2 (walkforward) | not written | Deferred until Stage 1 has 7+ days |
| 3 (wire) | not written | `CC_COMBINE_GATE_REGIME_ENABLED` in `cc_from_derivation.py`, ENABLED=False first |

**Existing per-cell walker** (`h_cc_combine_walker.py` → `cc_combine_gate.json`) keeps its role for regime × band × day unanimous 7-day overrides. Currently HOLD 0/27 cells cleared. Stage 1 provides a coarser regime-granularity fallback for when the per-cell walker never clears.

## Stage 1 SHIP criterion

All four required:
- `n >= 500` (pooled)
- `pooled_improve_pct >= 3.0` vs live `max`
- Both halves `>= 2.0%` improve vs `max` (chronological split by obs_time)
- Regime NOT in `CCD_SKIP_REGIMES = {se_flow, unknown}` (Ccd falls back to Pirate cc there — no wire target)

## Day-1 SHIP set (2026-09-02)

| Regime | Formula | n | Pooled Δ | Halves A / B |
|---|---|---|---|---|
| frontal | random | 595 | +5.20% | +4.45% / +5.75% |
| ne_flow | random | 1,736 | +7.88% | +6.10% / +10.42% |
| pre_frontal | random | 5,711 | +5.65% | +4.14% / +6.89% |
| sea_breeze | random | 2,087 | +5.13% | +3.98% / +6.31% |

## Correctly-demoted regimes

- **se_flow** (Stage 0 +6.44% STABLE ★) → `SKIP-ccd`. Ccd already falls back to Pirate cc on se_flow per [[project_cc_is_blend_of_clchcm]]; no wire target.
- **sw_flow / nw_flow / calm** (Stage 0 pooled >0 but UNSTABLE) → `SKIP-mag`. Halves A negative, halves B strongly positive — reads as recent-anomaly contamination that Stage 0's `both positive` bar missed. Watch for stability restoration.

## Clock

- Day 1/7 as of 2026-09-02
- Earliest wire-eligible = **2026-09-09** (day 7/7 with STABLE SHIP set and no HOLD days)
- Stage 2 walkforward-stability script when Stage 1 has 7+ days of history

## Wire path (Stage 3, deferred)

`cc_from_derivation.py` already has scaffolding:
- `_derive_with(formula, cl, cm, ch)` handles arbitrary formula key
- `_derive(cl, cm, ch)` uses module-level `FORMULA = "max"`
- `CC_COMBINE_GATE_ENABLED = False` for per-cell walker (existing)

Stage 3 adds:
- `CC_COMBINE_GATE_REGIME_ENABLED = False` (new flag)
- `_COMBINE_GATE_REGIME_PATH` pointing at `weather_collector/data/cc_blend_formula_regime.json`
- Precedence: per-cell walker gate (existing) > per-regime gate (new) > module `FORMULA` default

Ship in two commits: (a) reader + telemetry-only; (b) flip after 7-day live observation.

## Related

- [[project_cc_is_blend_of_clchcm]] — the underlying "cc is derived from cl/cm/ch" architecture
- [[project_cc_combine_walker]] — the per-cell walker (regime × band, complementary role)
- [[feedback_hypothesis_promotion_pipeline]] — the 4-stage pattern this follows
