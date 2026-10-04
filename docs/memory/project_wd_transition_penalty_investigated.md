---
name: wd-transition-penalty-investigated
description: 08-10 investigated the +88-115% wd mismatch penalty. Root cause is model-input error; no post-hoc fix. wdp already at current-optimal config.
metadata: 
  node_type: memory
  type: project
  originSessionId: b8058893-d7b5-4544-a4d3-9f9dee94eef7
  modified: 2026-08-10T16:30:42.196Z
---

# Finding

`regime_transition_audit` reports wd MAE penalty of +88-115% on mismatch rows (state_fc.regime != state_obs.regime) across every band with monster n (n=28,463 mismatch rows). 08-10 pair-log workup on `error_l1` / `error_l2` / `error_wdp` cross-cut by mismatch-type × band:

**L1 fallback vs top-of-stack on mismatch rows (per-band):**
- 0-5h: L1 -9.5% (marginal L1 win)
- 6-11h: L1 -11.6% (marginal L1 win)
- 12-23h: L1 +3.3% (top slightly wins)
- 24-47h: L1 +1.9% (top slightly wins)

**Uniform-90° prior:** +25-35% WORSE than top-of-stack across all bands.

**Per-cell:** mixed. Some cells favor L1 by 20-40%, some favor top by 15-70%, no systematic pattern. wdp doesn't consistently beat L1 on mismatch cells outside the 4 SHIP cells already-live.

# Why

When the model gets the regime wrong (state_fc.regime != actual), the entire wd forecast chain is drawing on wrong inputs. L1 raw is wrong. L2 blends are wrong. wdp persistence assumes obs-time regime is a proxy for near-future — which the mismatch label directly refutes. Every post-hoc correction layer inherits the underlying error.

**No amount of layer surgery fixes source-input error.** This is a model-quality question (better regime classifier at forecast time, ensemble spread proxy) that lives outside the correction stack.

# wdp already at optimal

Live `wd_persistence_gate_curated.json` contains exactly the 4 SHIP cells the 08-10 Stage 2 verdict proposed:
- calm/12-23 (delta -30.74%)
- calm/24-47 (delta -17.60%)
- se_flow/0-5 (delta -17.01%)
- sw_flow/0-5 (delta -37.82%)

The verdict "Move to Stage 3 wiring" is stale template output — wiring IS Stage 3, wdp reads this JSON at runtime. No additional promote work needed.

# Actionable (small, separate scope)

**UI intervention** — at forecast time, detect leads where `state_fc[lead].regime != state_curr.regime` (regime transition ahead, detectable pre-obs). Widen displayed compass band or grey out the specific bearing on such leads.

**Data plumbing DONE 2026-08-10 v0.6.401c.** `derived.state_fc_by_lead` (array of regime_synoptic per hourly lead) is now published to weather_data.json alongside `derived.state.regime_synoptic`. Any frontend consumer computes transition mask as `[fc[i] != state_curr for i in range(n)]`. Extracted from wd_persistence_gate's per-lead classifier + moved to `state_stamp.py`. Smoke test 08-10: state_curr=pre_frontal, 3 transitions detected at leads {9,39,42}.

**Frontend consumption not implemented.** Requires PWA design decision on how to render "wd uncertain" (band widening vs. hide vs. label) and on which surface (Right Now compass, 48h chart, Wind Impact card). When that design lands, the data is ready to be read.

# How to apply

If someone flags the +88-115% wd transition penalty as a candidate investigation, read this. Answer: investigated 08-10, no post-hoc fix, wdp already tuned. Redirect to (a) source-side model improvements (out of scope) or (b) UI intervention.

Related: [[project_wd_persistence_gate]], [[project_wd_l3_l4_circular]], [[project_wd_l2_blend]], [[feedback_asymmetric_gates_hide_signal]].
