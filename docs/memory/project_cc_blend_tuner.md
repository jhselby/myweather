---
name: cc-blend-tuner
description: "Stage 0 tuner (h_cc_blend_formula.py) comparing max / random / max-random overlap formulas for Ccd composition per regime. First run 2026-07-31 on 123K quads: STAGE 0 HOLD — max wins in 8/10 regimes; frontal +4.3% for random but halves-unstable; nor_easter +30.9% but data one-sided (all in second half). One clean per-cell candidate: pre_frontal/0-5h random +3.5% n=2,115. Re-check ~08-07 when frontal + nor_easter accumulate."
metadata: 
  node_type: memory
  type: project
  originSessionId: 434af779-9797-4cea-bd88-1e0939ffeef0
  modified: 2026-07-31T12:55:26.668Z
---

# cc composition tuner — h_cc_blend_formula.py

**Shipped:** 2026-07-31 v0.6.390e. Analysis-only, not wired.

**Purpose:** For each synoptic regime, empirically pick the best overlap formula for computing cc from cl_l6/cm_l6/ch_l6:
- **max** — `max(cl, cm, ch)` (HRRR's convention, Ccd today)
- **random** — `100·(1 − Π(1 − x/100))` (independent layers, sum of complements)
- **max_random** — `max(cl, cm)` treated as contiguous adjacent deck, then random with ch (ECMWF/GFS convention)

## First run (2026-07-31, filter obs_time ≥ 2026-07-01, n=123,317 quads)

### Overall
```
max          24.276  ← baseline
random       25.099  (−3.39% vs max)
max_random   25.150  (−3.60% vs max)
```
Max is the right global default. Both alternatives LOSE globally.

### Per regime (n ≥ 100)
| Regime | n | best | gain vs max | halves? |
|---|---|---|---|---|
| sw_flow | 38,090 | max | — | — |
| se_flow | 22,508 | max | — | — |
| pre_frontal | 19,119 | max | — | — |
| nw_flow | 18,220 | max | — | — |
| ne_flow | 11,968 | max | — | — |
| sea_breeze | 5,775 | max | — | — |
| calm | 3,829 | max | — | — |
| **frontal** | 1,959 | random | **+4.29%** | **UNSTABLE** (A=−2.12%, B=+7.82%) |
| unknown | 1,608 | max | — | — |
| **nor_easter** | 241 | random | **+30.85%** | one-sided (A=8, B=233) |

### Per regime × lead-band (n ≥ 50) — ★ ≥ +3% non-max win
- **pre_frontal / 0-5h** — random +3.52% (n=2,115) ★ CLEAN CANDIDATE
- frontal / 0-5h — random +23.39% (n=213) — small n
- frontal / 6-11h — random +12.65% (n=228) — small n
- nor_easter / 12-23h — random +27.70% (n=70) — thin
- nor_easter / 24-47h — random +32.17% (n=93) — thin

## Interpretation

**Max wins globally.** HRRR's convention is empirically the right default at KBVY. This is a legitimate NEGATIVE result — worth knowing, saves future relitigation.

**Frontal is suggestive but not shippable.** Pooled +4.3% for random overlap, but halves-unstable (coin flip between halves). Could be one storm dominating the sample. Need 2-3 more frontal passages to trust.

**Nor_easter data is one-sided.** All 233 of 241 rows sit in the second half of the window (recent July nor'easter). Genuinely can't halves-verify until a nor'easter passes with enough temporal separation from this one.

**pre_frontal / 0-5h is the closest thing to a real signal.** n=2,115, +3.5%, in a common regime, per-cell rather than per-regime. Worth carrying forward as a Stage 1 halves-verify candidate independent of the regime-level table.

## Next actions

1. **Re-check ~08-07** — 7 more days of frontal + nor_easter data. Same script, same threshold. If frontal halves stabilize positive AND nor_easter halves become viable, promote to Stage 1.
2. **Optional Stage 1 for pre_frontal/0-5h cell** — halves-strict re-fit on 30-day window. If it holds ≥+3% on both halves independently, wire as a per-cell override (regime-conditional lookup in Ccd) rather than a regime-level table.
3. **Consider adding to daily digest** — currently one-off. Adding to `analysis/` and giving it a KNOWN_LIVE_PIPELINES entry would surface any signal drift automatically.

## Design gate for wire

Any composition change to Ccd requires:
- Pooled gain ≥ +3% vs max
- Both halves ≥ +1% positive (halves-stability)
- n ≥ 200 in the relevant slice
- No lead-band actively worse than max within the slice

## Files

- `analysis/h_cc_blend_formula.py` — the tuner
- `analysis/output/h_cc_blend_formula.txt` — latest output

## Related

- [[project_cc_derived_field]] — architectural framing (derived-with-tunable-composition)
- [[project_lc_regime_conditional]] — Lc failure that motivated the Ccd/cc-question
- [[feedback_pooled_n_time_thin]] — why halves-verify matters even at n>1000
