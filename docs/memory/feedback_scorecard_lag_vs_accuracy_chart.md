---
name: scorecard-lag-vs-accuracy-chart
description: Debug page top scorecard reads time_series_diagnostic.json (7-day window); the accuracy-over-time chart below reads mae_over_time.json (multi-week). They can disagree by design when a recent ship is still rolling through. Reconcile before diagnosing.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fc21901e-1b40-4198-b923-f7d96e236bec
  modified: 2026-07-29T13:01:10.651Z
---

Two dashboards on `corrections_debug.html` measure "pipeline vs raw" MAE with **different windows** and **can visibly disagree**:

- **Scorecard banner** (top, `renderScorecardBanner`) — reads `time_series_diagnostic.json`, written by `decay_fit.py` with `TIMESERIES_DAYS = 7`. Pooled over the last **7 days only**.
- **Accuracy-over-time chart** (lower, `mae_over_time.json`) — accumulating multi-week history, one point per obs-day.

**Why:** codified 2026-07-29 after Joe read the scorecard showing ws +15.9% (regression) and expressed disappointment, but the accuracy chart underneath showed ws corrected tracking raw normally. The 7-day scorecard was still dominated by 6 days of pre-fix data (wind_blend BLEND_HOURS 24→4 shipped 07-28 in v0.6.384) while the day-1 post-fix read was −2.5% vs raw. The scorecard is a **lagging indicator** by construction and can misrepresent post-ship reality for up to a week.

**How to apply:**
- When Joe asks "why has X gotten worse" or "why is field Y regressing" and the scorecard is his evidence, **first check `mae_over_time.json` for the per-day trend** before diagnosing a new problem. The regression may be pre-fix data still inside the 7-day window.
- Read the per-day trend directly:
  ```
  python3 -c "import json; d=json.load(open('.../mae_over_time.json'))['series']['ws']; \
    days=sorted(d['raw'].keys())[-14:]; \
    [print(day, d['raw'][day]['mae'], d['prod'].get(day,{}).get('mae'), \
      f\"{(d['prod'][day]['mae']/d['raw'][day]['mae']-1)*100:+.1f}%\" \
      if day in d['prod'] and d['raw'][day].get('mae') else '') for day in days]
  ```
- When a recent ship changes a field's pipeline behavior, the scorecard will lag by up to 7 days. Not a bug — the tile is answering "how has the last week gone."
- If a recovery narrative is expected, note it in the corresponding post-ship watch entry with the day-1 verify result so a reader landing on the scorecard has context (pattern used in v0.6.384 watch entry).

Related: [[project_wind_blend_blend_hours_fix]] (if written), [[feedback_debug_page_canon]].
