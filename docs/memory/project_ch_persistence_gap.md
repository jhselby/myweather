---
name: ch-persistence-gap
description: "2026-07-11: ch structural investigation — pipeline behind persistence at every lead band, at every regime except frontal. Sharply lead-concentrated: lead 1 skill −2.19 (persist MAE 8, L4 MAE 26); narrows to ~−0.15 at leads 20+. L3+L4 doing real work (L1 33 → L4 26 at lead 1) but ceiling is bad. **Fix design (Joe's insight, 07-11 evening): regime-gate — L4 for `frontal` only, persistence for all other regimes. Estimated pooled ch MAE 25.64 → 20.61 (~20% reduction).** Cheaper + cleaner than per-lead blend. Fits existing skip-table architecture. Same class likely applies to cl/cm."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2bd018ca-98b4-4343-badc-7b405cae24be
---

## What we found

Follow-on to [[project-persistence-skill-baseline]] which surfaced ch as NO SKILL across every lead band. Sliced ch by (regime), (exact lead), (valid-time hour):

**By regime:** 8 of 9 diffuse — L4 behind persistence at sw_flow, se_flow, nw_flow, pre_frontal, ne_flow, calm, sea_breeze, unknown. Only `frontal` (n=4,705) flips positive (+0.058). Not regime-concentrated.

**By exact lead — the sharpest cut:**
| lead | MAE_pers | MAE_L1 | MAE_L4 | skill_L4 |
|---:|---:|---:|---:|---:|
| 1 | 8.2 | 31.7 | 26.0 | **−2.19** |
| 5 | 17.6 | 34.9 | 26.5 | −0.51 |
| 10 | 20.3 | 37.0 | 25.0 | −0.23 |
| 24 | 21.7 | 42.5 | 25.5 | −0.17 |
| 47 | 22.7 | 39.8 | 26.6 | −0.17 |

- Lead 1: persistence MAE = 8 vs L4 MAE = 26 → pipeline is 3.2× worse. "ch 1 hour ago" is devastating.
- Gap narrows sharply through leads 1-10 as persistence MAE rises.
- Leads 10-47: both stuck at their ceilings (persist ~22, L4 ~26). Pipeline behind by 4 pts at *every* long lead.

**By valid-time hour:** all UTC hours BEHIND; worst 18Z (~2pm local, −0.45) and 06Z (~2am local, −0.36). Secondary; afternoon convection is where HRRR ch is wrongest.

## The story

**L3+L4 are doing real work.** L1 raw MAE 33 → L4 MAE 26 at lead 1 (20-45% improvement across every regime). The stack works.

**But the ceiling is bad.** HRRR ch at this site can't get below MAE ~25 at any lead. Meanwhile persistence at long lead sits at ~22 because ch is diurnally correlated — "ch now" looks similar to "ch 24h ago." HRRR can't beat that diurnal echo.

**Only frontal regime clears persistence** because during real frontal passage ch is tied to synoptic dynamics HRRR captures well.

## Design — regime-gated architecture (Joe's insight, 07-11 evening)

Sharper than a per-lead blend: **use L4 only in the one regime where L4 beats persistence (`frontal`); use persistence-of-obs everywhere else.** Maps directly onto the existing skip-table architecture (v0.6.279): the gate lives in the same place, on the same axis (regime_synoptic), stamped at forecast time so live-decidable.

**Estimated impact (n-weighted mean of by-regime MAE):**
- Current L4 pooled ch MAE: **~25.64**
- Proposed regime-gated MAE: **~20.61**
- Improvement: **−5.03 pp / ~20% ch MAE reduction**

For comparison: this is bigger than most field-level wins the pipeline has shipped in the past 2 months. Landmark-sized.

**Implementation sketch:**
```python
# in decay_apply.py, after L4:
if field == "ch" and regime_synoptic != "frontal":
    ch_forecast = obs_at_run_time_hour  # persistence fallback
# else: keep L4 output
```

Requires: (1) a stamp of `obs(run_time_hour)` reaching the pipeline for the ch key (currently obs_temp_log has 24h retention — enough for live gating, not for full-day audit); (2) the decay_apply.py change gated by regime; (3) Stage 4 audit hook to verify the regime classifier is right when the gate fires.

## Gates to clear before Stage 2

1. **Regime × lead cross-cut per [[feedback-regime-lead-band-cross-cut]].** `sw_flow` (n=51k, biggest sample) is nearly tied — skill −0.08. Is L4 losing sw_flow uniformly across leads or concentrated at short lead? If long-lead L4 wins sw_flow, the gate should be regime×band not just regime.
2. **Orthogonality-analog.** Is a "ch regime skip" additive to what the existing `l3_regime_lead_analysis` + skip-table already captures? Or would adding ch to the skip-table with regime-specific skips give the same win?
3. **7-window agreement** per standard [[feedback-whitelist-promotion-gate]].

## Cross-field generalization

Same story likely applies to **cl** and **cm** — both showed NO SKILL in [[project-persistence-skill-baseline]]. If HRRR's cloud-cover parameterization structurally underperforms persistence except during synoptic events, all three cloud fields may need the same regime-gate. Quick slice check queued.

## Deprecated framing (my original persistence-blend proposal)

Original proposal was a per-lead linear blend `w(L) × obs + (1-w(L)) × L4` with several weight schedules. Retained here as note: the regime-gate above is cleaner, fits existing skip-table architecture, and larger in expected impact. Per-lead blend was over-engineering for the actual failure pattern.

## Follow-ons queued

1. Build `h_ch_persistence_blend.py` next session (~1-2h).
2. If Stage 0 magnitude shows meaningful skill gain, promote to Stage 2: wire a `ch_persistence_blend.py` processor into collector, live-off, shadow-log a week.
3. Meta-question this raises: which other fields might have the same story? cl/cm both showed NO SKILL — they may benefit from the same architectural change. Check with the same slicing.

## Cross-refs

Related: [[project-persistence-skill-baseline]], [[project-cm-stage4-degradation]] (cm same class), [[project-correction-stack]], [[project-todo]].
