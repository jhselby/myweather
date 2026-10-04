---
name: l1-only-field-routing-trap
description: "When any L1_ONLY_FIELDS entry gains an L2+ correction, `mae_over_time.py`'s L1_ONLY branch must be updated to prefer explicit error_l1 over top-level `error` (which is L2-view once fc = wd_l2). Otherwise raw == L2 in the aggregate and every \"vs raw\" trend read for that field is silently a \"vs L2\" read."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 49547252-cd8d-4eff-b0cf-640d7facf514
  modified: 2026-08-02T12:14:53.503Z
---

**Rule:** When shipping a new correction for any field in `mae_over_time.py`'s `L1_ONLY_FIELDS`, audit the L1_ONLY reader branch (lines ~137-165). It must read `error_l1` first and fall back to `error` only for pre-correction rows. Never treat `error` as raw for these fields — `forecast_snapshot.py:246-249` sets top-level `entry[field] = entry[f"{field}_l2"]`, so `error = fc − obs = wd_l2 − obs = error_l2` after L2 ships.

**Why:** For wd, wind_blend shipped 2026-07-20 v0.6.368a. The L1_ONLY reader kept routing `error` to the `raw` bucket. Result: `raw` == `l2` on every daily rollup, `prod_real` never emitted, `wd` looked chronically "L1-forever" in every field-health scoreboard from 07-20 → 2026-08-02. Any trend read for wd during that window was L2-vs-L2, invisible to the sentries. Discovered 2026-08-02; fixed same day by (a) preferring `error_l1` in the L1_ONLY branch and (b) emitting `prod_real` inline from the deepest specialist present.

**How to apply:**
1. Any new L2/L3/L4/specialist shipping for a field must add its `error_<layer>` to the pair-log writer (`forecast_error_log.py`) — the wd path already does this correctly.
2. In the same PR, update `mae_over_time.py`'s L1_ONLY branch so `raw` reads `error_l1` first, and `prod_real` gets the deepest-specialist error inline (L1_ONLY doesn't get applied_layer stamping).
3. After deploy, force one `mae_over_time.py` run with `MERGE_REFRESH_DAYS=30` so the poisoned aggregate history is overwritten. Otherwise the old L2-labeled-as-raw numbers persist for 30 days.

Related: [[feedback_shadow_write_applied_layer_trap]] — different pathway, same class of failure (metric-plumbing bug hides real forecast behavior for weeks, sentries silent). Both traps live in the pair-log → mae_over_time pipeline.
