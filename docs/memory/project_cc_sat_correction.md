---
name: cc-sat-correction
description: "KILLED 07-20 same-day after sanity check. Stage 1 finding was 80% rediscovery of Lc — script measured Δ against L1 baseline while Lc was already applying same Δ in production. One narrow finding survived: pre_frontal 0-5 for cl (regime-conditional beats Lc's fc_cl bin)."
metadata: 
  node_type: memory
  type: project
  originSessionId: d0ce8e13-443e-4221-9625-a6ecbc9e587f
  modified: 2026-07-20T15:21:26.722Z
---

# CC-saturation additive correction — INVESTIGATED AND KILLED (07-20)

**Status: killed same day** after sanity check exposed the finding as
mostly a rediscovery of Lc. See [[feedback_measure_against_live_stack_baseline]]
for the class of mistake.

## Original claim (07-20 AM)
Stage 1 preview via `h_rh_saturation_stage1.py`:
- 80 SHIP cells (cl 19 / cm 29 / ch 32)
- +40-79% MAE reductions on cc-saturated rows (fc_cc ≥ 80%)
- Δ = obs - fc = −50 to −70pp systematically

## Sanity check finding (07-20 PM)
Script measured Δ against pair log's `forecast` field, which carries
**L1 semantics** for cloud fields — even when L4 and Lc are live in
production. Real bias measurement on post-Lc-ship subset (n=643,
2026-07-17 onward):

    field   obs   L1   L4   L6(Lc)   bias_L4   bias_L6
    cl     42.1  29.3  29.5  12.9    -12.6     -29.2
    cm     16.8  63.1  56.4  24.2    +39.6      +7.4
    ch     16.0  94.2  59.9  21.4    +43.9      +5.4

Lc already gets ch bias to +5, cm to +7. My "correction" was
rediscovering the same Δ Lc applies.

## Alternative approach test (regime-conditional cl)
Did `obs_cl` vary enough by regime at fc_cc≥80% to justify replacing
Lc's fc_cl-binned correction with a (regime × band) correction?
- Yes — obs_cl varied 6.6 to 52.8 across cells
- BUT halves-stability failed. Δ_A vs Δ_B fluctuates 14-57pp across
  the 06-30 mixture seam.
- Only 1 SHIP cell (pre_frontal 0-5) beat Lc halves-stable.
- Verdict: Lc's fc_cl-binned approach wins on all-time training data.

## What survived
**Narrow finding for pre_frontal 0-5 cl:**  
Regime-conditional beats Lc by +23% winA / +40% winB in halves check.
Fog-during-front-approach pattern (obs_cl ~53) where Lc under-corrects
because fc_cl falls in a low-shift bin. Worth flagging IF a future
narrow-promote gate emerges, but not worth a full processor.

## What's dead
- `h_rh_saturation_stage1.py` — still runs in daily digest, but its
  "80 SHIP" claim is meaningless because it uses wrong baseline. Should
  be rewritten with per-field baseline (L1 for cl pre-Lc, L4 for ch
  pre-Lc, L6 for all post-Lc) OR skipped in favor of Lc.
- `<field>_cc_sat_correction_curated.json` files (3 of them, unwired
  preview outputs) — orphan data, no consumer.

## Lessons
See [[feedback_measure_against_live_stack_baseline]].

## Related
- [[c1_pivot_to_confidence]] — C1f cc-saturation is the confidence axis
- [[lc_flip_outcome]] — Lc live 07-17 v0.6.355; 16 SHIP cells
