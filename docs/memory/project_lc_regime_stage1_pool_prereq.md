---
name: project_lc_regime_stage1_pool_prereq
description: Stage 1 regime-Lc gate fix 2026-08-08 — pool-must-also-ship prereq. Diagnoses the Stage 1 vs walkforward tension.
metadata: 
  node_type: memory
  type: project
  originSessionId: 7c9d7aa9-9a64-4be2-8251-1d31c6c73f86
  modified: 2026-08-08T10:38:50.564Z
---

**Fix shipped 2026-08-08 v0.6.397 session (analysis-only, no collector deploy).**

`h_lc_regime_stage1.py` now demotes regime SHIP cells to `SKIP-nopool` when the pooled-Lc for the same (field, bin) doesn't also SHIP. Cuts today's SHIP count 72 → 61 (11 demoted).

**Why:** For weeks Stage 1 was reporting PROMOTE 70+ SHIP cells while `walkforward_lc_regime` rejected regime-Lc as -3.60% vs pooled on held-out. Same pair-log, same day. The gap was Stage 1's promotion criterion:

- Halves-stability WITHIN the training window ≠ generalization to held-out.
- Worst class: `(field, bin)` where pool decided "no correction" (e.g. `ch/pre_frontal/0-5` raw=pool=5.52), regime fits noise per-regime, applies a "correction" that reverses on held-out → `reg=15.53` on test = -181% loss. Small-n per-regime cells overfit easily.

**How the fix works:** After both regime + pooled loops complete, walk regime cells. If verdict is SHIP but `(field, bin) ∉ pooled_ship_set`, demote to SKIP-nopool. Updates `regime_ship_set`, `verdict_counts`, cell payload verdict.

**What's still not caught:** "Regime fires stronger than pool on fit window but fails on held-out" — cells where both pool and regime ship, but regime overfits. Would need `regime_must_beat_pool_by_X_on_halves` gate — bigger change, not done today. Walkforward remains the authority for that class.

**Why the two-script split still exists:** Stage 1 is a daily tripwire — cheap "any regime-Lc signal today?" check. Walkforward is authoritative for held-out generalization. Both are useful; they measure different things.

**Independent finding vindicating cc/cl retire arc:** Walkforward showed pool_vs_raw for cc = -3.91% and cl = -51.32%. Lc itself is net-negative on those fields at this window. No regime-conditional trick could rescue what pooled is losing. Consistent with [[project_lc_regime_conditional]] cl off (v0.6.389f), cc retired → Ccd (v0.6.390).

**Gate reset:** Fix changed SHIP set → history shows CHURN → next streak starts today.
