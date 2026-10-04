---
name: l2-no-stage-gate
description: "L2 additions are architectural, not per-cell — add first-principles, refine later. Do not run L2 through the L3/L4 Stage 0→3 gate pipeline."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8780e2e1-8f86-471c-9c52-3d9999517eaf
  modified: 2026-07-20T17:46:46.230Z
---

# L2 additions skip the Stage 0→3 gate pipeline

L2 = observation-blend layer. If a field is observable at Marblehead and the model publishes a forecast for it, L2 blends the observation into the near-lead forecast. That's a first-principles decision, not a per-cell one.

L3/L4 are error-correction layers with per-cell verdicts, so they require the [[feedback_hypothesis_promotion_pipeline]] Stage 0→3 gate. L2 does not.

**Why:** Blending an obs into a forecast is the same operation regardless of regime/lead-band. The only design decisions are HOW (linear vs circular vs vector-mean), decay window length, and low-signal floors — those are one-time engineering calls, not per-cell verdicts to gate on.

**How to apply:** When Joe says "add X to L2," don't propose a Stage 0 exploration script. Implement the L2 blend directly. Refinements (τ tuning, per-octant additive, K-taper style) come later as Group D refinements once pair-log evidence has accumulated post-ship.

**Precedent:**
- ws/wg L2 in `wind_blend.py` — just exists, no Stage 0 trail
- Humidity K-taper (v0.6.218) — Group D refinement AFTER L2 humidity was already live
- Per-octant ws L2 additive — currently Stage 0, but that's a *refinement* to existing ws L2, not a new-field add

**Anti-example (07-20):** Claude proposed a Stage 0→3 path for adding wd to L2. Wrong — apply the [[feedback_hypothesis_promotion_pipeline]] to L3/L4/specialist candidates only, not to L2 additions.

## Related
- [[feedback_hypothesis_promotion_pipeline]] — the 4-stage path applies to L3/L4/specialists, NOT L2
- [[feedback_regime_gate_first]] — regime-conditional cell-level verdicts; L2 doesn't have those
