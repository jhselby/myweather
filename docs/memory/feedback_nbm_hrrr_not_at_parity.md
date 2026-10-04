---
name: nbm-hrrr-parity-definition
description: "Parity = architectural equivalence (same processors, same mechanisms, same layer stack). NOT data-state, ENABLED flags, or pair-log maturity. Don't conflate the two. Updated 2026-08-26 after v0.6.499 native L2 completed structural parity."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f98aaa56-0f4c-4ee8-a7d4-432f6e02dd1f
  modified: 2026-08-26T17:04:34.529Z
---

**Rule:** parity is an *architectural* claim — same layer slots, same mechanisms, same math shape. It's silent about data state, curation, or runtime flags.

**Why:** Joe corrected me twice on 2026-08-26. First when I claimed parity while the L2 was still delta-transfer (an architectural gap). Second when I claimed non-parity because the NBM skip table was under-populated + L6_NBM had ENABLED=False + pair log was thin — those are NOT parity gaps.

**The distinction:**
- **Parity gap (architectural):** a processor slot doesn't exist on the NBM side. e.g. before v0.6.499, native L2 didn't exist for wind/cloud — that was a real parity gap.
- **Data project:** a table is empty or under-curated. e.g. skip_table_nbm_curated.json having 8/49 cells is a data project, not a parity gap. The table + apply mechanism exist.
- **Runtime decision:** an ENABLED flag is False. e.g. L6_NBM ENABLED=False is an operational call about whether to fire, not a missing architecture. The processor + curated table + apply site exist.
- **Calendar:** deeper NBM layers have <10d of live pair-log rows. Time fills it. Not a parity gap.

**As of v0.6.499 (2026-08-26):** HRRR/NBM are AT PARITY. Every layer slot exists on both sides with mirrored mechanisms. Native L2 covers all 8 NBM-scope fields (t/h/dp via additive Kalman, ws/wg/wd via wind_blend, cc/ch via cloud_obs_blend, sr identity because HRRR has no L2 for sr either). Everything downstream is data + operations.

**How to apply:**
- When asked "are we at parity" — answer based on architecture only.
- When cataloging "what's left," separate parity gaps (architecture), data projects (curation/fits), runtime decisions (flags), and calendar (time).
- Don't roll them all into a single "parity" list — that confuses which lever fixes which.
