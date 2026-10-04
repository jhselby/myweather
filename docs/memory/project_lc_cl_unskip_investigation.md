---
name: project-lc-cl-unskip-investigation
description: Investigate whether Lc _FIELD_SKIP for cl can be lifted; today cl at W=all shows +35% held-out MAE improvement.
metadata: 
  node_type: memory
  type: project
  originSessionId: 9a1f61c0-0486-4626-81ae-ca4da37e80cb
  modified: 2026-08-14T13:24:31.010Z
---

Opened 2026-08-14 from #4 (Lc rolling window) triage. Not started — parked for a future session.

**Question**: Can cl come off `_FIELD_SKIP` in `weather_collector/processors/cloud_saturation_correction.py`? Today's `h_lc_rolling_window` shows cl at W=all held-out MAE improvement +35.01%. That's a large improvement being left on the table if the historical reason for skipping has passed.

**Why cl was skipped** (needs verification): removed from Lc in v0.6.389f (2026-07-30). The processor comment says "cl fully off Lc via _FIELD_SKIP" but doesn't cite the trigger. Best guess: cl's per-(regime, bin) bias had shrunk 4-38× or sign-flipped vs the pre-07-20 fit, dragging accurate forecasts into wrong territory (see docstring of `analysis/h_lc_rolling_window.py`). A shorter window was supposed to be the fix; the full lift was the bandage.

**Why now**: `h_lc_rolling_window` on 2026-08-14 (3d held-out) shows cl at W=all improves held-out MAE +35% while cm and ch also improve. If the "recent bias shift" that motivated the skip has stabilized, the bandage is now costing us.

**How to answer**:
1. Reconstruct the state around 2026-07-30 — what was `h_lc_rolling_window`'s cl verdict then? Was cl at W=all held-out MAE negative?
2. Run `h_lc_rolling_window --hold-days 7` and `--hold-days 14` today. Does cl at W=all stay positive across longer hold-outs?
3. Split cl held-out MAE across the last 30 days into halves. Sign-flip = still unsafe. Both halves positive = safe to un-skip.
4. If safe, remove `"cl"` from `_FIELD_SKIP`, redeploy, watch cl Prod-vs-raw for 7 days.

**Related**:
- [[project_lc_regime_conditional]] — regime-conditional Lc is a separate axis; not a substitute for un-skipping cl.
- [[project_pipeline_to_good]] — reprioritize this if it stays actionable.
