---
name: feedback-digest-review-includes-debug-page
description: "Daily digest triage must include the debug page's staleness banner (OPEN_WATCHES past close date), not just DIGEST.txt. The staleness audit lives on corrections_debug.html and is easy to miss if scope is narrowed to the digest file."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 23b5871a-fdee-47f7-9ac1-9e9135a084ab
  modified: 2026-08-18T13:11:50.043Z
---

Daily digest review must include the debug page's staleness audit, not only `analysis/output/DIGEST.txt`.

**Why:** the staleness audit ("⚠ Staleness audit — N watches past close date") is auto-computed from the `OPEN_WATCHES` array in `corrections_debug.html`, not from any digest script. If session-start review reads only `DIGEST.txt`, closing watches slip past silently and rot the open-work list. Joe caught this on 2026-08-18 when I missed the dpbp 08-18 close in my morning triage even though I had read the full 3441-line digest.

**How to apply:** at the top of any session that starts with a digest-review prompt (e.g. Joe pastes `DIGEST.txt` or asks "anything for today"), also grep `corrections_debug.html` for `OPEN_WATCHES` entries whose `closeDate ≤ today`. Surface each in the triage. Any close needs: (a) CLEAN vs UNCLEAN verdict, (b) remove from `OPEN_WATCHES`, (c) update the day-X/14 line item, (d) mirror to `MEMORY.md` (move from active to settled/do-not-reopen), (e) update the memory file itself.

Related: [[feedback_digest_triage_discipline]] · [[feedback_debug_page_canon]] · [[feedback_debug_page_full_sweep]].
