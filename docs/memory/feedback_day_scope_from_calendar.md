---
name: day-scope-from-calendar
description: "Session-start: read corrections_debug.html Calendar block for today's dated entries as the day-scoped to-do list. Digest = tools that ran; Calendar = decisions scheduled to be made today. Missing the second lens skips items."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ee219fc7-b19d-45bb-958f-2e0e51617443
  modified: 2026-07-25T01:01:17.979Z
---

At session start, before triaging the digest, grep `corrections_debug.html` for today's date (`Fri MM-DD` and today's ISO) inside the Calendar block AND Upcoming decisions block. Those entries are the day-scoped to-do list.

**Why:** 2026-07-24 session. I triaged the morning digest, misread the C1h stability tick as a ship recommendation, spent the session fixing the registry backstop and shipping cl_persistence_gate Stage 3. All good work — but never looked at the Calendar. Two Fri 07-24 items (sr Lsb Stage 3 halves re-run, h_ws_octant_bias re-read 2/3) were scheduled for today with defined decision criteria. Both scripts ran in the morning digest but I never read the verdicts against the decision criteria. Joe had to point at the Calendar block for me to notice.

The digest tells me *what tools ran*. The Calendar tells me *what decisions Joe expected made today*. Different lenses; both required.

**How to apply:**
1. Session start (or immediately after digest triage): `grep -n "<today's Fri date>\|<today's ISO date>" corrections_debug.html | head -20`
2. Read each hit's decision criteria + the digest verdict for the referenced script.
3. Report which trigger fired (SHIP / HOLD / MARGIN / no-change) so nothing gets silently skipped.
4. Move outcomes to Recent activity per debug page's "outcomes move to Recent activity" rule.

**Also update:** Upcoming decisions block (`Upcoming decisions`) is a second source with more structure (Q/E/D lines). Sweep both.

## Related

- [[feedback_debug_page_canon]] — debug page is source of truth. Calendar + Upcoming decisions are load-bearing views of today's work.
- [[feedback_digest_triage_discipline]] — digest triage is necessary but not sufficient; Calendar sweep is the missing second lens.
- [[feedback_verify_completeness_claims]] — related failure family: claim "I handled today's work" without running the check that would prove it.
