---
name: deploy-hygiene-publisher-pairs-analysis
description: "Any commit touching a Python file in analysis/ that is listed in publisher/main.py:PUBLISHERS must be paired with `make deploy-publisher` in the same session. The publisher CF bundles analysis/ into its image at deploy time; commits without a deploy don't reach production until someone else deploys."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 39396d72-ba15-4563-b4ac-84d727899d4e
  modified: 2026-09-07T23:43:40.392Z
---

# Rule

**When you commit a change to `analysis/*.py` that is in the `PUBLISHERS` list of `publisher/main.py`, run `make deploy-publisher` in the same session.**

Current `PUBLISHERS` list (as of 2026-09-07, `publisher/main.py:41-60`):
- `mae_over_time`
- `gate_firing_rollup`
- `h_persistence_skill`
- `h_pp_platt_calibration`
- `h_pp_bin_calibration`
- `pp_brier_reliability`
- `scoreboard_v2`
- `per_field_scoring`
- `nbm_l2_delta_audit`

If you touch any of those files (including definitional changes, bug fixes, docstring updates that affect output, or metric semantic shifts), the CF must redeploy to pick up your change.

## Why

**Real incident, 2026-09-06 → 2026-09-07:** v0.6.554 was committed 09-06 15:10 EDT with a scoring fix for `analysis/per_field_scoring.py` (the `_selected_l1_error` NBM fallback). The commit message read "Selector Skill card was mislabeling picks post-L3_NBM kills." The fix was correct.

But the publisher CF was last deployed 2026-08-26 — 12 days before that fix landed. Every hourly publisher tick from 09-06 15:10 EDT to 09-07 10:58 UTC kept overwriting `gs://myweather-data/per_field_scoring.json` with the pre-fix output. Joe's morning digest at 06:24 EDT ran the fixed local code and overwrote the GCS file to green; the publisher clobbered it back to red at 07:00 EDT. The tile flipped red → green → red every hour for 44 hours.

Joe wasted a session investigating a metric that his own fix had already resolved because the deploy step didn't happen. The `make deploy-publisher` command takes 90 seconds and is idempotent. Skipping it is the failure mode.

## How to apply

1. **In the same commit workflow as the analysis-file change**, immediately after `git push`, run `make deploy-publisher`. Do NOT batch multiple analysis changes across days without deploying — the risk multiplies with time.

2. **After deploy, verify** with:
   ```
   gcloud functions describe myweather-publisher --region=us-east1 --gen2 --format='value(updateTime,serviceConfig.revision)'
   ```
   The `updateTime` should be within the last few minutes; the revision string should be new (`myweather-publisher-000NN-xxx`, incremented).

3. **For extra confidence on a metric-semantics ship**, wait for or trigger the next hourly publisher run and re-fetch the GCS JSON. Confirm `generated_at` reflects the new run and the metric values match what your local code produces.

4. **Applies specifically to:** any change that would affect the computation output of a script in the `PUBLISHERS` list. Cosmetic-only comment changes don't need a deploy.

5. **Enforcement:** this rule should eventually be a git pre-push hook that checks the diff and refuses to push touching a `PUBLISHERS`-listed file without a deploy stamp in the same session. Until then it's a manual checklist item.

Related: [[feedback_deploy_sequence]] (general collector/publisher/frontend deploy ordering) · [[feedback_verify_completeness_claims]] (verify things actually happened) · [[feedback_analysis_tools_drift_from_runtime]] (the meta-problem: analysis code drifting from what's actually running).
