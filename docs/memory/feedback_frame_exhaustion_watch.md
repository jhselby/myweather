---
name: feedback-frame-exhaustion-watch
description: "When metrics have been flat for 2+ weeks AND Stage 0 hypothesis surfacing has produced mostly CLOSED MISS, the FRAME is exhausted — meaning the current input+correction-stack combination has been fully squeezed inside what the pair log can measure. Stop building new same-shape hypotheses; do a frame audit and expand the input set. Established 2026-08-18 after 6 weeks of grinding while NWS gridpoint / NBM sat unused as a forecast source."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 23b5871a-fdee-47f7-9ac1-9e9135a084ab
  modified: 2026-08-18T14:10:40.728Z
---

Frame exhaustion is a real, recognizable state, and the workflow was silently ignoring it for weeks.

**Definition:** the current *input frame* (data sources fed into the pair log) plus the current *correction stack* has been fully exploited when:
- 7-day MAE hasn't moved ≥3% on any field for 21+ consecutive days
- Stage 0 hypothesis surfacing has produced mostly CLOSED MISS for 14+ days
- Recent ships are dominated by anti-scar-tissue refactors that ship neutral by design

When these three coincide, the pair log has told us everything it can. Grinding on ever-smaller signals inside it produces subtractive knowledge only ("here's one more thing that doesn't work") and no user-visible skill gain.

**Why the workflow doesn't catch it on its own:** the daily digest is a closed loop over the pair log. Every script (Stage 0 sensors, gate walkers, regression sentries) can only find signal *within* what the pair log contains. Nothing on the daily cadence asks "should the pair log be different?" That question requires stepping OUT of the loop, which the ritual doesn't include.

**How to apply — recognize the state:**
- At session start, after loading state per [[feedback_session_start_load_project_state]], check the mae_over_time.json for any field that's moved >3% on 7-day-rolling MAE in the last 21 days. If none: raise frame exhaustion.
- Scan the last 14 days of commits for a CLOSED MISS pattern. If ≥3 same-class closes: raise same-class exhaustion.
- Track "ship counts by impact class" per [[feedback_ship_count_by_impact_class]]. If skill-ship count is 0 for a 2-week window, that's confirmatory.

**How to apply — respond to the state (mandatory):**
- STOP building new Stage 0 hypotheses inside the current pair log.
- STOP proposing new dynamic-gate migrations beyond items already in-flight.
- Do a frame audit: `ls weather_collector/fetchers/` to inventory what's fetched, grep for downstream use of each fetch, ask "what data are we not consuming that would raise the ceiling?"
- Propose one input-frame expansion (add a new source, activate an unused source, add a new axis). This is the workstream for the next 2-3 weeks.

**Historical anchor for future sessions:** 2026-08-18 discovered NWS gridpoint (NBM-derived official NWS forecast for our grid cell) had been fetched at every tick for months and used only for the briefing narrative text. Not in the pair log, not benchmarked, not consumed as a forecast source. Direct symptom of frame exhaustion going unrecognized. v0.6.431 activated it.

**Related:**
- [[feedback_ship_count_by_impact_class]] — the categorization that makes exhaustion measurable
- [[feedback_session_start_load_project_state]] — the load pass that must include an exhaustion check
- [[feedback_co_owner_posture]] — "every ~4 weeks do a frame audit" — this is the mechanism the frame audit should watch for
- [[feedback_stop_after_minimum_ship]] — when frame is exhausted, minimum ship = zero, and that's honest
