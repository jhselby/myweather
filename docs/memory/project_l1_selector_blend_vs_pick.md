---
name: project-l1-selector-blend-vs-pick
description: 2026-09-22/23 diagnosis of why L1 selector plateaus and the blend-weight regressor proposal to replace binary picking. Framing-lock-in critique + prototype plan on h/nw_flow/24-47h.
metadata: 
  node_type: memory
  type: project
  originSessionId: fe1df4d3-dc96-4742-ade8-dbc8d711cb10
  modified: 2026-09-23T21:13:02.117Z
---

# L1 selector: why it's bad + blend-weight proposal

Session 2026-09-22 → 2026-09-23. Joe: "why is the selector so bad, will it improve, don't be cagey."

## Why it's bad (three compounding reasons)

1. **Blind until v0.6.644.** Selector picked with regime × lead-band aggregate features — every obs in the same cell got the same pick. No per-obs signal. The v2 per-obs classifier (v0.6.644–646) fixes this; only 1/18 Stage-0 cells has cleared Stage 1 so far (h/nw_flow/24-47h, +6.50% test, 19.9% oracle capture).
2. **Binary picks amplify error asymmetrically.** Wrong pick = full HRRR–NBM gap. Slightly-off blend weight = fraction of gap. Classification loss is discontinuous — 51/49 confident and 99/1 wrong pay the same penalty. Bad fit when both sources are usually partially right.
3. **HRRR-dominant fields swamp signal.** ~80% base rate → classifier learns "always pick HRRR" → Stage 1 correctly rejects as no-lift. Real signal lives in minority-regime tails where n is thinnest. See [[feedback_stage0_shadow_lift_gate_hrrr_dominant]].

## Ceiling of the picking framing

**Estimated ~20-30% of oracle gap, ever.** Remaining 70%+ is bleed from the binary choice itself — cases where truth is 40/60 HRRR/NBM and any pick pays half the gap. No feature engineering fixes that; baked into problem shape. h/nw_flow/24-47h at 19.9% is probably near-peak, not a floor.

## SHIPPED 2026-09-23 as v0.7.0 — see [[project_09_23_session]]

13 curated cells across dp/h/ch/wg/t. Halves-stable lifts +7% to +56% vs best single source. Shadow only (BLENDER_APPLIED_ENABLED=False). Debug page tile live under Applicability map. Progressive rollout dp → h → ch → wg → t once plumbing verified on fresh data.

**h/nw_flow/24-47h validation held:** blender +30/+43% vs classifier's +6.5%. ~5-6× the classifier's capture on the same cell — confirms the blend framing is the correct one.

## Why hasn't this come up before?

Three honest reasons, in weight order:

1. **Framing lock-in.** Selector born as routing question ("when is HRRR broken enough to abandon?"), not fusion question. Once named "selector" with Stage 0/1/2/3 built around discrete picks, every iteration was a picking iteration. Blending path exists elsewhere in stack (L4 NBM cascade, cc_combine, wd L2 blend) in different code with different gates — nobody wrote "what if L1 selector were a blend."
2. **Promotion pipeline is built for discrete decisions.** Orthogonality gates, KILL verdicts, walkers, SHIP/HOLD/KILL — all assume bit-flip. Continuous weight breaks most of that machinery. Infrastructure inertia is why the bad framing persisted.
3. **Might have been tried and rejected.** Model doesn't have full session history. Plausible prior session considered blend and rejected — e.g., can't cleanly fall back to known-good source when features look weird, or naive 50/50 lost. **Check before building.**

## Open question for next session

Before building blend-weight prototype: **has this been tried?** Search prior sessions for "blend weight", "regressor", "continuous selector", "L1 fusion". If yes, why rejected? If no, proceed to step 1.

## Links
- [[project_l1_selector_per_obs_axes]] — the 09-19 diagnosis this builds on
- [[project_09_21_session]] — v2 classifier build (7 commits, 4 deploys)
- [[project_09_22_session]] — most recent session context
- [[feedback_stage0_shadow_lift_gate_hrrr_dominant]] — base-rate rejection pattern
