---
name: feedback-fitter-vs-runtime-feature-availability
description: "Before shipping a learned classifier live, audit that every training feature has a runtime producer. Fitters and runtime feature-builders drift silently."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 74a7659c-1484-4905-a27a-29ebad782615
  modified: 2026-10-01T13:19:34.542Z
---

Before promoting a learned classifier (GBM, logistic, or any model that reads a named feature vector) to runtime use, audit that every feature the fitter trains on has a live producer at inference time.

**Why:** 10-01 session discovered sr learned_gbm had been shipped twice (v0.7.15, v0.7.18) and never fired a single time, because `cross_run_spread.py` was never producing `xr_spread` for sr. The v5 fitter trained with real `xr_spread` values from the pair-log; runtime's `_build_learned_features` emitted `xr_spread=None` on every sr call; the predict path's fail-safe None-check short-circuited to band_pool silently. The ship existed in the curated JSON but was mechanically dead for ~2 days before attribution-check caught it. See [[project_10_01_session]].

**How to apply:** When a fitter emits a new runtime-ready table (`l1_learned_selector_curated.json`, blender cells, etc.) for a FIELD that wasn't previously classifier-wired:

1. Grep the fitter's feature-build code for its feature-name list and training-time source.
2. Open the runtime feature-builder (`forecast_snapshot._build_learned_features` for the learned selector) and verify every feature in the fitter's list has a producer that returns non-None for the target field.
3. Specifically for cross-field feature producers (`cross_run_spread.FIELDS`, derived values, hourly arrays): check the field is in the producer's allowlist. These are the usual silent-drift locations.
4. On the first post-deploy tick, verify the shadow stamp (`{field}_learned_pick_shadow`) appears in the pair-log for ANY row with the covered regime+band. Zero shadow stamps = the predict path is still fail-safing, likely a missing feature.

Related: [[feedback_shipped_flag_verify_effect]] — verify by pair-log attribution stamp, not just the flag. The feature-availability audit is the pre-ship complement; the attribution-stamp check is the post-ship complement. Both are needed.
