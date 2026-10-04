---
name: orthogonality-gate
description: "Stage 0 magnitude isn't enough — always run orthogonality vs existing axes before promoting a hypothesis. Two same-day kills on 2026-06-24 came from candidates that passed magnitude tests but failed ortho."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a933ef0e-f53e-46b4-802a-0d1b833732d0
---

When a Stage 0 script shows a hypothesis elevates MAE on some axis, that's a magnitude finding, not a signal-independence finding. Before promoting to Stage 2 (production wiring), the next gate is orthogonality vs every existing axis the new hypothesis could be confounded with.

**Why:** On 2026-06-24, two Tier-2 candidates passed magnitude tests cleanly then failed orthogonality the same day:

- **wind_shift_rate** showed rotating ≥80° class elevates ch +33%, cm +24%, cc +15%. Ortho check (`analysis/h_wind_shift_rate_orthogonality.py`): 1 ORTHO / 22 REDUNDANT / 2 CONFOUNDED / 11 AMBIGUOUS vs C1a. C1a (regime transition flag) already captures the signal — wind shifts and regime transitions co-occur. The Stage 0 elevation was real; the signal was just a noisier restatement of C1a.

- **C1g (RH ≥95% fog)** showed cm +134%, ch +149%, pa +2893% MAE elevation in the saturating-humidity bin. Ortho check (`analysis/h_c1g_orthogonality.py`) vs C1f (precip_fc>0) and cc-saturation (cc_fc≥95): 1 ORTHO / 69 REDUNDANT. When you marginalize over the unused axis and inspect the F=False or S=False subsets, fog rows actually have *smaller* MAE than non-fog (ratio 0.02–0.25× across cl/cm/ch). The Stage 0 elevation was sampling-driven — fog naturally co-occurs with rain forecast and high cloud cover. Once you control for those, fog has no independent widening signal.

Both candidates had textbook Stage 0 numbers. Both would have shipped as duplicate signal had they skipped the gate.

**How to apply:**

1. **Every Stage 1 promotion requires a paired orthogonality script.** Pattern: `analysis/h_<axis>_orthogonality.py`. Cross-tab the candidate axis against EVERY existing C1 axis (currently: C1a transition, C1b cluster spread, C1c pressure tendency, C1e post-frontal, C1f precip_fc) and architecturally adjacent axes (cc-saturation, etc.).

2. **Marginalize over unused axes, don't condition on them.** When testing axis X vs axis Y, sum across all other axis values to avoid sample-thin cells. Conditioning on `Y=False AND Z=False` will produce false REDUNDANT verdicts because the (G=True, Y=False, Z=False) intersection is too sparse to fire. (This bug bit me in the first C1g ortho run — fix was the `cell_marginalize_S` / `cell_marginalize_F` helpers.)

3. **Verdict thresholds (current convention):**
   - ORTHOGONAL: candidate ratio ≥1.30× in both axis subsets (independent elevation persists when other axis is off AND on)
   - REDUNDANT: candidate ratio ≤1.10× in axis-off subset (signal vanishes — captured by other axis)
   - CONFOUNDED: candidate ratio ≥1.30× only in axis-on subset (signal is just a co-occurrence echo)
   - AMBIGUOUS: between thresholds

4. **Promotion gate: ortho cells ≥ ~8** across the matrix (9 fields × 4 bands × N axes-to-test). C1f cleared 23 ortho — the strongest result so far. C1e marginal at 6 (and weakening). wind_shift_rate at 1 and C1g at 1 both killed.

5. **Same-day verdict is the goal.** Stage 0 → ortho check → debug page update → kill or ship. Don't let a Stage 0 finding sit in the Stage 1 backlog for a week — orthogonality is a known-method check, doable in one script, one cache stream. Sitting time produces "we think this is real" momentum that's harder to revert.

Related: [[feedback-hypothesis-promotion-pipeline]], [[feedback-debug-page-canon]], [[project-hypothesis-backlog]], [[project-c1-pivot-to-confidence]].
