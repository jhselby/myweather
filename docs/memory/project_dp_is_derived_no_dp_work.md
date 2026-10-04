---
name: project-dp-is-derived-no-dp-work
description: "dp is Magnus(t, h) with observed_dp also derived, so any dp-side correction is architecturally a patch for an upstream t or h bias. Default is to NOT open dp workstreams — investigate t or h instead. Not a ban: a dp workstream is live if it has a clear reason (signal that genuinely can't route through t/h, or dp-side is cheaper/cleaner even knowing it's a bandage). Bar is high but not closed."
metadata: 
  node_type: memory
  type: project
  originSessionId: 23b5871a-fdee-47f7-9ac1-9e9135a084ab
  modified: 2026-08-30T11:03:00.909Z
---

# dp is derived — do not open dp workstreams

**Opened 2026-08-18** after Joe asked: "why are we doing dp work when dp is purely derived from t and h?"

**The physics:** `dp = Magnus(t, h)`. `observed_dp` is also `Magnus(observed_t, observed_h)` (`obs_log.py:80-86` overwrites even direct sensor readings). So `dp_error = f(t_error, h_error)` with zero independent signal. Any dp-side correction is either redundant with a t/h correction, or masks a t/h bias it should be attributed to.

**Why:** debugging feels harder when the metric you're fixing isn't the metric with the bug. Fixing dp when the actual defect is in h means:
- Future h-side fixes will interact unpredictably with the dp bandage
- You lose the attribution signal — was the win from the h fix or the dp bandage?
- The bandage will silently rot when the upstream h regime changes
- New engineers/sessions won't know why the dp specialist exists

**How to apply:**

1. **Default: don't open new dp workstreams.** If a dp regression shows up on the per-field snapshot, first re-scope as "which upstream field (t, h) is biased?" and investigate that. dp-side is a live option, not the reflex.
2. **A dp-side Stage 0 needs a stated reason** why upstream t/h is not the right home — e.g. signal that genuinely can't be captured by an h or t correction (non-invertible transform, noise-mixing), or a case where the dp-side patch is cheaper/cleaner and the architectural cost is accepted. Bar is high but not closed.
3. **The one existing exception (dpbp, LIVE since v0.6.391) should be reconsidered.** Empirically wins (+9.63% pooled dp MAE) but architecturally patches an h or t bias in `pre_frontal/nw_flow/sw_flow @ lead≥6h`. The correct fix is to route the equivalent correction into h or t so future h/t work interacts predictably. Migration is a follow-on workstream — not urgent (watch closed CLEAN 08-18) but should happen before the next dp specialist ships (there won't be one under this policy).
4. **Related dp gates that stayed OFF are validated by this principle:** `dp_residual_persistence` (ENABLED=False), `h_dewpoint_depression` verdict "invest in t layers instead", `h_dewpoint_depression_stability` all-UNSTABLE. Those refusals were correct even before this principle was written.

**Same principle applies to cc** — `cc = Ccd(cl, cm, ch)`. cc is in `_FIELD_SKIP`. Ccd is a composition function on the derived layer, not a correction on cc directly. The cc combine walker ([[project_cc_combine_walker]]) tunes the composition formula, which is legitimate — it's tuning the derivation, not correcting the derived output.

**Related:**
- [[project_cc_is_blend_of_clchcm]] — same "derived fields inherit" principle for cc
- [[project_dpbp_live]] — the exception to be migrated
- [[project_hypothesis_backlog]] — item #6 (dpbp precursor) was the last dp workstream that should have opened
- corrections_debug.html:3193 — the debug-page annotation that already documented this and was ignored when dpbp shipped
