---
name: feedback-selector-prod-vs-prod
description: "When building a selector/router that picks between multiple source cascades, compare fully-corrected Prod-per-source (post-cascade output MAE), never raw-per-source. Raw comparison hides HRRR-side cascade depth and produces wrong picks that regress user output."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 0987755d-ce9c-4540-a7e2-2dab3448cc43
  modified: 2026-08-19T15:48:36.997Z
---

# Rule

**When picking between multiple source cascades (HRRR vs NBM in option-1, or any future N-source selector), compare the FULLY-CORRECTED Prod output per source — never raw source MAE.**

For each row in the pair log:
- HRRR Prod = `error_{deepest_applied_hrrr_layer}` walking priority `dpbp/wsbp/wdp/clp/chp/l6/l5/l4/l3/l2/l1`
- NBM Prod = `error_l3_nbm` (or deepest NBM layer once cascade grows)

Then argmin per (field, band).

## Why

Raw comparison silently loses cascade depth on the side with more layers.

**Concrete example (2026-08-19 v0.6.436 → v0.6.440):**
Phase 4 selector was built comparing raw HRRR MAE vs raw NBM MAE per (field, band). For ch:
- HRRR raw MAE = 29.3
- NBM raw MAE = 19.4 → **raw-comparison would pick NBM** ✗
- BUT HRRR Prod (with Lc + chp specialists) = 11.5
- NBM Prod (l3_nbm ≈ raw_nbm today) = ~19.4

Selecting NBM for ch based on raw comparison would overwrite user-visible ch with l3_nbm (~19.4 MAE) and **lose the 8-MAE-point win** from Lc+chp corrections.

Prod-vs-Prod comparison correctly picks HRRR: 11.5 < 19.4.

**Ship gate is unchanged.** Both raw and Prod comparisons pick NBM for router-scope cells (t/ws/wd @ leads ≥6h) because HRRR-side there has only L2, and NBM raw beats L2. But for fields with deep HRRR corrections (ch/cm/cc via Lc/chp; sr via Lsr/Lsb; dp via dpbp), raw comparison is wrong.

## How to apply

1. When building any selector/router/argmin picker between source cascades, the compare function MUST use per-source Prod not per-source raw.
2. If Prod-per-source isn't available in the pair log yet (e.g., during warmup), the selector should fall through to the incumbent source, not fabricate a decision from raw MAE.
3. Fit publishers (like `l1_selector_fit.py`) that read the pair log should walk a per-field layer priority list to determine "deepest applied HRRR-side layer" rather than trusting the top-level `error` column (which is L2 by legacy convention — see [[feedback_pair_log_error_field]]).
4. When explaining the selector to Joe (or in code comments), always frame the comparison as "which cascade delivers lower MAE", not "which source is stronger". The former is the shipping question; the latter is academic.

Related: [[feedback_pair_log_error_field]] (top-level error = L2 residual, not deepest applied), [[08-19-afternoon-handoff]] (session where this rule was learned).
