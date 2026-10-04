---
name: shadow-write-applied-layer-trap
description: Shadow arrays written unconditionally for flip-gate visibility (v0.6.382p pattern) must not be walked by applied_layer stampers. Guard forecast_snapshot.py:_derive_applied_layer with specialist ENABLED check when wiring any new Stage 3 dormant gate.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 94111ec9-cb6f-4d6c-96fe-e0ac130f618b
  modified: 2026-08-02T11:59:04.743Z
---

Any specialist that writes a shadow array unconditionally (so ENABLED=False still populates the pair log for flip-gate scoring — v0.6.382p pattern) will poison applied_layer stamps unless explicitly gated.

**Why:** `forecast_snapshot.py:_derive_applied_layer` walks specialist keys and stamps `applied_layer=<specialist>` whenever the shadow differs from the prior layer. Shadow differs by construction. Stamp then flows into Fitter's `per_layer_mae_by_lead[.].production` and `mae_over_time[.].prod_real` — both looked catastrophically bad for cl 07-27 → 08-01 while real production was fine. Silent for 5 days because shadow happened to track raw closely.

**How to apply:** When wiring a new dormant specialist (dpp, wgp, wsbp, dpbp, etc.):
1. Add the module import to `forecast_snapshot.py` top.
2. Add the ENABLED guard clause inside `_derive_applied_layer` next to the clp/chp/wdp guards (v0.6.390j added the pattern).
3. When the specialist flips ENABLED=True, the guard auto-lifts. No coordination needed.

Also add the shadow array to the `layers` dict at forecast_snapshot.py:~120 following the clp/chp/wdp template.

**Historical-poison cleanup.** The v0.6.390j guard stops *new* poisoning but does nothing about pair-log rows already stamped wrong. Those live for 30 days in the rolling pair log and keep the regression_sentry / field_skip_sanity screaming daily. On 2026-08-02 we shipped a one-shot backfill for cl at `analysis/backfill_cl_applied_layer.py` — it re-stamps `applied_layer` on cl rows by mirroring `_derive_applied_layer`'s own value-walk against the per-layer errors, then republishes to GCS. When dpbp/wsbp/etc. flip through this trap in the future, parameterize `FIELD` + `POISONED_STAMPS` in that script and rerun the same flow (backfill → `mae_over_time.py` with `MERGE_REFRESH_DAYS` bumped to cover the poisoned window → `gsutil cp` back to GCS).

Related: [[feedback_persistence_gate_shadow_write]] (the sibling shadow-write bug in the gate itself, fixed v0.6.382p). This trap is downstream — same shadow, different consumer.
