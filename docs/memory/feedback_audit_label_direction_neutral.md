---
name: feedback-audit-label-direction-neutral
description: "When naming a confound in an audit label, do not prescribe a direction (\"discount\", \"inflate\", \"trust more\") unless you can prove the direction holds across all correction shapes. Name the confound; let the reader interpret."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-04T14:53:15.907Z
---

# Rule

Audit labels that name a confounder (weather difficulty, sample thinness, regime shift, etc.) must **name the confound without prescribing an interpretation direction**.

Wrong: "discount weekly correction lift accordingly."
Right: "interpret weekly correction gains in that context."

Wrong: "trust the 7-day number over the 3-day when they disagree."
Right: "7-day and 3-day disagree — either window can lag the other after an intervention; cross-check per-cell."

The direction of a confound often depends on the correction's shape (constant-absolute-help vs proportional vs fixed-shift-that-overshoots), the field's error distribution, or the regime mix. Prescribing a direction is only correct for one of those cases and wrong for the others.

## Why

08-04 session: I wrote "raw difficulty >1.0 = raw model itself struggled more than usual; discount weekly correction lift accordingly." Joe: "is 'discount weekly correction lift accordingly' too strong?"

Directionally wrong for the >1.0 case. A fixed-effect correction that subtracts a constant absolute error shows SMALLER % lift on hard weeks (raw big → % of raw shrinks even with same absolute help) and LARGER % lift on easy weeks. So "discount on hard weeks" is backwards — the lift is understated, not overstated. On easy weeks the direction flips.

The safer framing names the confound but doesn't prescribe an action. The reader — who knows the correction's shape and the cell-level reads — can interpret correctly.

## How to apply

- Every audit label / footnote / tooltip that mentions a confound: read it back and check whether the prescribed action is unambiguously correct across all plausible correction shapes.
- If direction depends on the correction: strip the direction. Use "interpret X in this context" or "cross-check against Y" instead of "discount / inflate / trust more."
- Explicit direction is fine when the math forces it (e.g., "sample thinness → wider confidence interval, treat any % gap under 5% as noise" — that's a floor rule, not a signed direction).
- When in doubt: name the confound, don't tell the reader what to do.

Related: [[feedback_measure_before_concluding]], [[feedback_pooled_n_time_thin]], [[project_raw_difficulty_index]].
