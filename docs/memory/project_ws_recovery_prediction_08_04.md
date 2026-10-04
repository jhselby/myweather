---
name: ws-recovery-prediction-08-04
description: "Falsifiable prediction logged 2026-07-29: if v0.6.384 wind_blend fix is the main ws@6-11h driver, Prod-vs-Raw regression should trend down each day through 08-04. Flat/worse = residual damage beyond fossil-contamination."
metadata: 
  node_type: memory
  type: project
  originSessionId: 73429c93-7451-4383-be7a-18cb78ea6325
  modified: 2026-07-29T16:48:35.806Z
---

# ws Recovery Prediction — check against outcome on 08-04

Logged 2026-07-29 to keep post-hoc rationalization honest. This session diagnosed ws@6-11h scoreboard regression of +75% MAE vs raw as primarily fossil-contamination from pre-v0.6.384 (07-28) `BLEND_HOURS=24` stale-blend, now aging out of the 7-day rolling scorecard window.

**Prediction:**

If fossil is the main story, `ws@6-11h Prod-vs-Raw` (scorecard "WORST CELL" tile) should trend DOWN each day between 07-29 and 08-04 as the 7-day rolling window replaces pre-fix days with post-fix days. Not perfectly monotonic — regime noise will wobble it — but the trajectory should be clearly downward, ending under ~30% by 08-04.

**Milestones:**

- **08-04** (day 7 post-fix): 7-day window fully post-fix. Also wsbp flip decision same day.
  - **Success:** ws@6-11h < 30% → fossil-contamination confirmed as main driver. Continue watching skip-table effectiveness through 08-11.
  - **Partial:** 30-50% → fossil was significant but residual damage exists. Investigate what L3 is doing at 6-11h beyond the 2 shipped SKIP cells (07-28 v0.6.386).
  - **Failure:** > 50% → fossil hypothesis was wrong or incomplete. Full re-audit of ws correction stack at 6-11h needed.

- **08-11** (day 14): ws L3 SKIP watch expires. Clean read on whether the 2 new skip cells are net-positive on their own.

**Additional watch:** biggest-field-regression tile should shift OFF ws entirely if wash-through succeeds — currently ws +15.9% pooled. If ws remains biggest regression after 08-04, same investigation applies.

**Why this memory exists:** without a pre-committed prediction, "of course it was fossil, we knew that" gets adopted regardless of what actually happens ([[feedback_measure_before_concluding]] + [[feedback_dont_invent_numbers]] extended to include predictions).

Related:
- [[project_ws_l3_skip_table]] — v0.6.386 skip cells (day 1/14)
- [[preflight_wsbp]] — wsbp flip 08-04
- [[project_ws_l3_long_lead_regression]] — L2 stale-blend diagnosis
- [[feedback_debug_page_canon]] — scoreboard is truth
