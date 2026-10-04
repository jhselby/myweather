---
name: pp-brier-reliability
description: "pp Brier reliability decomposition script (`analysis/pp_brier_reliability.py`, scaffolded 2026-07-21). Fills measurement gap flagged on debug page line 1347. Two findings: (1) pp decay stack delivers +6.7% Brier improvement / +0.0523 skill vs L1 that no debug-page chart ever shows because pair-log `forecast` for pp carries L1 semantics (v0.6.372 joiner fix booked). (2) pp systematically under-forecasts wet outcomes across 10-90% bins (worst gap −27pp at 30-40% bin: predicts 35% → observes 62%). Stage 1 calibration-correction candidate booked."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0a14e1f9-f87a-464e-846e-dcdd5c525ad4
  modified: 2026-07-21T23:32:45.056Z
---

# pp Brier reliability decomposition — 2026-07-21 scaffold + findings

## The script

`analysis/pp_brier_reliability.py` — bins pp forecasts by predicted-probability
decile (0-10%, 10-20%, ... 90-100%) and reports:

- **Per-decile calibration:** predicted mean vs observed frequency + gap.
- **Murphy 1973 decomposition:** Brier = Reliability + Uncertainty − Resolution.
  - Reliability: calibration gap (lower better).
  - Resolution: discrimination — how much do bins differ from base rate (higher better).
  - Uncertainty: irreducible baseline = base_rate × (1−base_rate).
- **Skill vs climatology:** 1 − Brier/Uncertainty. Positive = beats always-guess-base-rate.
- Split three ways: pooled all-bands, per lead band (0-5/6-11/12-23/24-47),
  and per correction layer (L1 raw / L4 post-decay / Production live).

Runs in daily digest from 2026-07-22 onward.

## First-run findings (2026-07-21)

Pair log: 179,739 pp rows; obs base rate 16.2%.

### Finding 1: pp decay stack delivers +6.7% Brier improvement — invisible until now

| Series | Brier | Skill vs climatology |
|--------|-------|----------------------|
| L1 (raw HRRR) | 0.10661 | +0.2147 |
| **L4 (post-decay)** | **0.09952** | **+0.2670** |
| Production (`forecast`) | 0.10661 | +0.2147 |

L4 vs L1: **Brier −6.7% (relative)**, skill Δ +0.0523. The pp decay
stack IS doing real work. But Production Brier == L1 Brier **bit-exact**
— pair-log `forecast` field for pp carries L1 semantics per
[[feedback_measure_against_live_stack_baseline]]. **Every debug-page pp
Production chart, Brier card, and scorecard "vs Persistence pp" line
has been rendering L1** for months. Users never saw the +6.7% improvement.

**Status update 2026-07-21 PM: proposed v0.6.372 joiner fix RETRACTED — not a bug, misread of historical pair-log data.** Traced the inconsistency to completion. Root cause: pp was dropped from L3_FIELDS on 2026-07-04 v0.6.304 (documented decision — L3 correction worsened MAE +4.2% Brier per the code comment at `decay_apply.py:78`). Pair-log retention is ~30 days, so my 179k-row analysis was ~2/3 pre-drop historical data (06-21 era) where pp WAS being corrected by L3 (L1=50, L4=54 pattern), plus ~1/3 recent post-drop data (07-12 → 07-21) where L1 == L4 bit-exact for **all 40k+ rows verified**. The Fitter's `time_series_diagnostic.json` aggregates over the more-recent window and correctly shows L1==L4==Production for pp — **the tsd is right, not wrong**. The +6.7% Brier improvement was a HISTORICAL artifact of a correction that was subsequently dropped, not a live bug. There is NO joiner fix to ship. Current state is correct-per-design. Everything works as intended.

**What survives as legit finding:** the under-forecast pattern (raw HRRR pp says 35% → observed 62%) IS real for the raw model. It's exactly the reason pp L3 was tried and dropped — per-lead decay helped Brier but hurt MAE. **A different mechanism** — bin-weighted probability lift table calibrating pp per predicted-decile — hasn't been tried and could work where per-lead decay didn't. That's a legit Stage 0 candidate (see follow-up item 2 below).

### Finding 2: pp systematically under-forecasts wet outcomes

L4 per-decile calibration (pooled all lead bands):

| Bin | n | Predicted % | Observed % | Gap |
|-----|---|-------------|------------|-----|
| 0-10 | 141,209 | 1.65 | 6.90 | −5.25 |
| 10-20 | 13,940 | 13.66 | 30.53 | **−16.87** ⚠ |
| 20-30 | 6,334 | 24.21 | 43.15 | **−18.94** ⚠ |
| **30-40** | 3,261 | 34.99 | 61.51 | **−26.53** ⚠ |
| 40-50 | 5,406 | 44.21 | 67.46 | −23.25 ⚠ |
| 50-60 | 4,511 | 54.61 | 66.13 | −11.52 |
| 60-70 | 2,007 | 64.63 | 79.37 | −14.74 |
| 70-80 | 1,254 | 73.25 | 64.67 | +8.58 |
| 80-90 | 1,521 | 85.15 | 69.76 | +15.40 ⚠ |
| 90-100 | 296 | 93.66 | 96.96 | −3.30 ★ |

Systematic **under-forecast** in the 10-70% bins — HRRR says "30%
chance" but it actually rains 62% of the time. Extremes (0-10, 90-100)
well-calibrated. The 70-90% bins over-forecast — small n but consistent.

Per lead-band pattern is the same shape; gap magnitude slightly larger
at short leads (0-5h: 30-40% predicted → 62% observed).

## Follow-up work booked (in [[project_todo]] P4 items 12/12a/12b)

1. **v0.6.372 pp Production=L1 rendering bug** — joiner fix. Small.
   Frontend auto-benefits.
2. **pp calibration Stage 1 candidate** — bin-weighted probability lift
   table. Add ~5-25pp to raw fc in the underforecast bins. Would need
   Stage 0 magnitude check first (pooling all bands may hide per-band
   structure). Standing re-audit via daily digest.
3. **pp τ tuning via Brier scan** — the script could be extended to
   sweep τ ∈ {7, 14, 28, 42} and pick min-Brier. Would resolve the
   dormant pp τ=28 validation gap that has sat unreviewed since 06-21.

## Related

- [[feedback_measure_against_live_stack_baseline]] — the pp `forecast` =
  L1 finding is the 3rd catch of this pattern this month (Lsr divergence,
  cc-sat kill, now pp Production rendering).
- [[project_todo]] P4 items 12, 12a, 12b — follow-up tasks.
- [[feedback_forecast_verification]] — persistence skill + pp Brier
  reliability were the two named measurement gaps; this closes the pp one.
