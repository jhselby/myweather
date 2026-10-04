---
name: feedback-hybrid-transition-pattern
description: "When shipping a backend key that fills over a rolling window (e.g., 7 days), the frontend should render a hybrid: real per-cell data where populated, approximation elsewhere. Coverage-threshold auto-drop for the approximation marker. Rationale: the alternative (wait N days before showing anything) hides signal; the other alternative (swap everything at once) misleads on partial windows."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 56248ef4-af78-48a9-998a-163e8a07965d
---

**The rule.** When a backend-computed aggregation (per_layer_mae_by_lead[field].production, per_layer_brier_by_lead.pp, etc.) fills over a rolling window rather than landing complete on the first Fitter cycle, the frontend should render a hybrid: use the real value at each (field, lead) where populated, fall back to a labeled approximation elsewhere. Include a per-card coverage threshold (e.g., ≥40/48 leads populated) that auto-drops the "approximation" marker on that field once real coverage is broad.

**Why:** 2026-07-01 shipped per-row applied-layer stamping → real Production MAE. Post-deploy, the Fitter's first cycle populated 9/48 leads per field (~184 rows total). Three shape options:
- (A) Show only the approximation until Production fills fully → hides real signal for 7 days; user can't verify the pipeline is working.
- (B) Swap all leads to the real key at first cycle → shows nulls for 39/48 leads; chart has huge gaps; wrong.
- (C) Hybrid — real where populated, approximation elsewhere. Marker stays until coverage broad.

Chose C. Immediate result: T's short-lead Production numbers dropped 15–40% vs the L6 approximation, exposing that L6 fires ~30% of rows (so approximation was pessimistic). Signal available on day 1, not day 7. `*` marker on Production/Production column self-explains the transition period.

**How to apply:**

1. **Backend emits the new key alongside existing ones.** Don't gate on completion; emit whatever's ready. Downstream can tell populated leads from null leads.

2. **Frontend hybrid helper.** For each (field, lead), return `real[lead]` only when it's both populated AND the per-lead sample count clears a minimum floor; else fall back to `approx[lead]`. Wrap chart data + table data + any derived aggregates (scorecard banner, etc.) through this single helper. Applied to any place the field-level metric surfaces.

   **Min-sample floor is not optional.** Without it, a lead with n=1 (a single unlucky pair) can dominate the chart. Set the floor high enough that MAE CI is ~±10-15% (n≥30 for typical distributions — matches the C1 curator's `MIN_N_MULTI`). The Fitter must emit the per-lead n array alongside the metric so the frontend can enforce this — e.g., `per_layer_n_by_lead[field].production` alongside `per_layer_mae_by_lead[field].production`. Caught this the same day it shipped when a T lead-8 with n=1 real=6.6 vs approx=2.6 would have appeared as a chart spike. See v0.6.274.

3. **Per-card coverage threshold + label swap.** Count populated real leads per field; drop the `*` marker on that field's card when count crosses the threshold. Don't gate globally (fields fill at different rates).

4. **Tooltip on the header exposes current coverage** (e.g., "Hybrid — real where populated (N/48 leads), approximation elsewhere"). Reader can eyeball progress toward full swap.

5. **Same pattern applies to `per_layer_brier_by_lead.pp` (populates first Fitter cycle post-emit, but same pattern generalizes) and any future backend metric that fills over a window.**

**See also:** [[project-07-01-session]] for the specific applied-layer stamping ship this pattern grew out of.
