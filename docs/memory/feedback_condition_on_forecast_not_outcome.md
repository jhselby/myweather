---
name: feedback-condition-on-forecast-not-outcome
description: "When a guard or gate acts on the FORECAST (e.g. raw cc >= 90 keeps raw), justify and re-test it on rows selected by the forecast, not on rows selected by the observed outcome. Selecting on the outcome (observed cc 95-100) makes the cautious forecast look good and hides the cost on every other row."
metadata:
  node_type: memory
  type: feedback
  modified: 2026-10-05T18:00:00.000Z
---

# Rule

If a gate fires on a forecast value, test it on the population the gate selects (forecast-conditioned), and report the outcome-conditioned slice only as a labeled sub-slice. Conditioning on the outcome is selection bias: it picks exactly the rows where the conservative forecast (raw) is right.

# Why (10-05)

Ccd's saturation guard (`SAT_THRESHOLD = 90`, raw cc >= 90 keeps raw) came from the 08-04 trace of rows with OBSERVED cc 95-100 (n=235): raw MAE ~2 vs Ccd ~30. The 10-05 decomposition (14d, complete cc/cl/cm/ch quads) conditioned on the raw forecast instead: with raw >= 90 (61% of 0-5h rows, 74% of 24-47h), raw scored 24.07 at 0-5h while derived-max scored 10.07; served 21.02. Both statements are true: overcast days are common and raw is perfect on exactly those; raw >= 90 is also wrong often when the sky is not overcast. The guard was fitted to the days it helps.

# How to apply
- For any guard, skip rule or threshold: state which variable it keys on (forecast, state, regime, outcome-free feature) and select the evaluation rows by that variable. Print the outcome slice (e.g. obs >= 95) beside it, never instead of it.
- When a post-hoc "trace the loss" investigation finds the loss concentrated in an outcome bin, that is a hypothesis for a forecast-conditioned test, not a finished justification.
- Related checks: [[feedback_fresh_fire_lucky_baseline_artifact]] (clear/overcast days make raw near-perfect), [[feedback_measure_against_live_stack_baseline]], [[feedback_check_contamination_before_acting]].

Related: [[project_10_05_session]] · [[project_08_04_session]] · [[project_cc_derived_field]]
