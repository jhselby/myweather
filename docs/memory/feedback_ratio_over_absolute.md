---
name: ratio-over-absolute-for-fast-metrics
description: "Fast-moving metrics (daily) should use ratio-to-baseline, not absolute values. Absolute daily MAE is dominated by weather noise; ratio (Prod-vs-Raw) cancels weather and isolates 'did we ship something bad.'"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6c13f0ec-2762-47f1-aab5-a15c48f08029
  modified: 2026-07-31T13:16:43.461Z
---

Fast-moving metrics (daily, single-tick) should be ratios to a baseline, not absolute values. Weather is noisy day-to-day — a stormy day pushes every field's MAE up together, so absolute daily MAE reads as "we broke something" even when the correction stack is fine. But a *ratio* like Prod-vs-Raw stays flat because both sides get worse together. The ratio only diverges when the correction stack does something the raw baseline doesn't — which is exactly the signal we want.

**Why:** 2026-07-30 designed the regression sentry after the Lc/cl breakdown went unnoticed for ~1-2 days. Joe asked whether we should add a 24-hour scoreboard alongside the 7-day. Direct answer would have been noise: yesterday's weather regime can move any field 3× normal without any code change. The correct answer was to use a ratio (Prod-vs-Raw), not an absolute (yesterday's Prod MAE alone). That way weather cancels; only ship-driven regressions surface.

**How to apply:**
- Any new daily-cadence alert or scoreboard tile: metric = f(Prod) / f(Raw) or (Prod - Raw) / Raw, NEVER f(Prod) alone.
- The same principle rules out "yesterday's Prod MAE" tiles that would sit next to "7-day Prod MAE" tiles. Skip them.
- Slow-moving scoreboards (7-day, 14-day watches) can use absolutes because the aggregation smooths weather noise. Fast-moving alarms cannot.
- If a metric intrinsically needs an absolute (e.g. "how much rain fell"), don't wire it as an alert — display it as reference, not signal.
- The `regression_sentry()` function in `build_executive_summary.py` is the canonical implementation. Threshold + min-consecutive-days at module top; tune these, don't reintroduce absolute-metric alerts.

**v0.6.390f refinement (2026-07-31): pair-window classifier, not single window.**
- A single trailing window lags interventions by its width. Flat 7d needs 7 days to reflect a fix; 3d needs 3 days. Neither is honest during the intervention lag — mixing bad-pre with good-post gives a "compromised" number that answers no question well.
- Fix: keep TWO ratios per field. `sustained` = trailing 7d weighted-by-n. `fresh` = trailing 3d weighted-by-n. Classify from the pair:
  - both hot (≥15%) → SUSTAINED FIRE (real, ship a fix)
  - sustained hot + fresh cool (<5%) → HEALING (intervention landed, watch it roll off)
  - sustained cool + fresh hot → FRESH FIRE (new regression, catch early)
  - both cool → clean
- Why pair beats decay: exponential weighting hides the tension between "sustained state" and "current state" in one blended number. The pair keeps them separate and turns the divergence itself into a diagnostic — HEALING is more informative than what a decay-average would show.
- Why pair beats "just show trailing-1d alongside 7d": single-day windows whipsaw on noisy days. Trailing-3d weighted keeps the alert stable while still surfacing genuine fresh changes.
- Rejected alternative: `known_bad_days.json` exclude registry — brittle, requires human maintenance, loses the intervention story (HEALING → CLEAN when we most want to see we're still watching).

**Related:**
- [[feedback_scoreboard_before_healthy]] — biggest-regression tiles first, positive framing second. Ratio metrics are what those tiles show.
- [[project_07_30_session]] — the session where the principle was designed and shipped.
