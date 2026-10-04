---
name: feedback-mixture-check-window-semantics
description: "c1_stage4_mixture_check uses RECENT_DAYS=7 vs CALIB_DAYS=7 (the 7d immediately preceding recent). Both windows slide. DEGRADED means 'the last 7 days are drifted vs the 7 days before that' — a moving drift detector, NOT a comparison to a fixed calibration baseline. Do not treat DEGRADED as 'chronic' or 'lingering from an older HRRR shift' — by construction, it's always about the past week's motion."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2612e533-b493-4573-96ed-5a4b19d7982c
  modified: 2026-07-29T17:01:47.890Z
---

## The rule

When c1_stage4_mixture_check.py reports DEGRADED on a cell, that verdict is derived from a **moving 7d recent vs preceding-7d calib window**. It measures fresh drift only, not accumulated drift from months ago.

**Why:** On 07-29, I anchored the reading of cm/0-5h [transition] b3 +42% DEGRADED to the 07-11 HRRR shift memory ("same signature, do nothing" then "re-curate per 07-11's two-week gate"). Joe corrected me: 07-11 was 18 days ago. I then looked at the audit script:

```
RECENT_DAYS = 7
CALIB_DAYS  = 7   # window directly preceding recent
```

Both windows are entirely inside the post-07-11 period. The 07-11 event cannot be what the mixture check is measuring today — that shift is baked into BOTH windows. The DEGRADED verdict is measuring **motion in the past week only**.

**How to apply:** When mixture_check surfaces a DEGRADED cell, don't:
- Cite an old HRRR event as the cause (it's in both windows equally)
- Recommend re-curating the c1 curated table (the daily 14d fitter is already absorbing the drift automatically)
- Assume the cell has been degraded for weeks

Do:
- Ask "what happened in the last 7 days" — recent ships, weather-regime shift, upstream HRRR/open-meteo notes
- Watch for acceleration across daily readings (e.g. cl/6-11h went +137→+217% in one day — that's real fresh movement)
- Trust the daily fitter to handle chronic drift; escalate only when acceleration continues across multiple readings

Related: [[project_cm_investigation_07_28]], [[project_stage4_audit]], [[feedback_scoreboard_before_healthy]].
