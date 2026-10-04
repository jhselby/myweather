---
name: feedback-apply-flip-invalidates-shadow-verifier
description: "Flipping a shadow mechanism to live-apply silently breaks the retro verifier that justified the flip: served == shadow, so lift collapses to 0% and the cell reads HOLD the next day. Before any apply-flip, check whether the verifier's baseline is row['error'] and preserve the pre-empted counterfactual."
metadata:
  node_type: memory
  type: feedback
  modified: 2026-10-02T14:10:00.000Z
---

# Rule

Before flipping any shadow mechanism to live apply, answer two questions **in the verifier's source, not from memory**:

1. **Where does the verifier's baseline come from?** If it reads the served value (`row['error']`, `error_prod`, `forecast` vs observed), then the moment the mechanism applies, served *is* the mechanism's own output. The comparison becomes mechanism-vs-itself and lift collapses to ~0%.
2. **Does the apply path destroy the counterfactual?** If the apply block overwrites the provenance stamp (`{f}_selector_source`, `applied_layer`) with its own name, the record of what *would* have been served is gone and the baseline cannot be rebuilt afterward. Retroactive repair is impossible — those rows are permanently unscoreable.

Both must be fixed **in the same ship as the flip**, or in a ship deployed before the next verifier run.

## Why

2026-10-02, v0.7.20 → v0.7.21. Flipped the L1 static blender's first cell (`h/nw_flow/24-47`, +35.5% lift, halves 38.7/33.9, n=436). `l1_static_blend_shadow_verify.py` took `served_mae` from `row['error']`. Because **every shadow-stamped row in a covered cell is also an applied row** once the cell is live, the entire population flipped at once: `served_mae == blend_mae`, `lift_vs_served_pct` exactly 0.0%. Against `min_lift_pct=5.0` the cell would have read **HOLD at 0%** the day after shipping — indistinguishable from the blend having stopped working, and landing directly on a scheduled verdict date. Demonstrated with a synthetic cell: `SHIP-READY (+80%)` with the fix, `HOLD (+0%)` without.

Worse, the apply block overwrote `entry[f"{f}_selector_source"] = "l1_blend"`, erasing the selector's would-be pick. `selector_mechanism` survived but names the *rule*, not the *source*, so it couldn't identify which cascade side to score against.

The near-miss: had this not been caught the same day, the most likely outcome was reading 0% as a regression and rolling back a mechanism that was in fact earning +35%.

## How to apply

- **Preserve provenance before overwriting it.** Stamp the pre-empted value (`{f}_preempted_source_shadow = source`) immediately before the apply block overwrites the real stamp. Naming it with the `_shadow` suffix lets it ride `forecast_error_log.py`'s generic `{short}_*_shadow` pass-through into the pair log with no writer edit — which otherwise has to be duplicated across the main and `wd` branches.
- **Teach the verifier a two-mode baseline.** `row['error']` for non-applied rows; a counterfactual rebuilt from the pre-empted source for applied rows, walking the same source-depth chain the runtime uses ("deepest available NBM layer wins" etc.). Mirror the runtime chain explicitly — don't assume one layer.
- **Drop unscoreable rows from the whole cell, not just the baseline series.** Applied rows logged before the provenance stamp existed have no counterfactual. Excluding them only from `served_mae` leaves the MAE series computed over different populations. Drop the row entirely and surface the count (`n_excluded_no_counterfactual`) in both the JSON and the text report so the gap is visible rather than inferred.
- **Expect a transition window.** Rows applied between the flip deploy and the provenance-fix deploy are permanently unscoreable. Keep that window as short as possible — ideally zero by shipping both together.

## Generalization

This is the shadow-verification mirror of [[feedback_shadow_write_applied_layer_trap]]. That rule says: when a mechanism applies, make sure the user-visible array gets the value, or you score something users never saw. This rule says: when a mechanism applies, make sure the *baseline* isn't the mechanism itself, or you score it against itself. Both failures are invisible — no error, no log line, just a number that looks plausible and is wrong. Same family as [[feedback_selector_prod_vs_prod]] (`prod` = error_l4 vs `prod_real` = error_{applied_layer}) and [[feedback_measure_against_live_stack_baseline]].

Checklist companion to [[feedback_shipped_flag_verify_effect]]: that rule says verify the mechanism fires. This one says verify the thing measuring it still measures anything.

## Related

- [[project_10_02_session]] — the session this came from.
- [[project_l1_static_blend_v076]] · [[feedback_analysis_tools_drift_from_runtime]] · [[feedback_fitter_vs_runtime_feature_availability]]
