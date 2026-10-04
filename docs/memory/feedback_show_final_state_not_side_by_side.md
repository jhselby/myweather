---
name: show-final-state-not-side-by-side
description: "For design review, show the final state directly (rip out old, put new in the same slot). Do NOT tuck a mock under existing content — Joe cannot visualize the post-change page from a side-by-side."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4c41e557-bb4a-4757-a036-04904a33e6db
  modified: 2026-08-25T16:52:48.589Z
---

# Show the FINAL state, not a mock-plus-old side-by-side

**Rule.** For design review work on the debug page, do the actual replacement — rip out the old block, put the new block in the same slot. Do NOT insert a mock alongside existing content and expect Joe to visualize the end state.

**Why:** On 2026-08-25 I inserted the new scoreboard mock BELOW the old value-chain scoreboard (under Current State, tucked under). Joe's exact response: "That work product is unacceptable — you left the existing shit as is and tucked the new shit under. no good. I want to see what the page is going to look like AFTER you make all the changes." He was right — a design mock only communicates when it's in the position it'll actually live, with the old thing gone.

**How to apply:**
- When Joe asks to review a design change, do the replacement in place. Comment out or delete the existing renderer/HTML; put the new HTML in that slot.
- If uncertain about placement, ask FIRST — don't build a "safe" side-by-side to avoid the decision.
- The design review then shows the actual future state, not a "compare with what's there today" split screen.
- Scoped CSS wrappers (`.sb-scope` etc.) are fine and expected for safety, but structural placement should be final.

**Related:** [[feedback_do_it_right]] · [[feedback_recommend_never_menu]] — pick a placement and commit to it, don't defer with a side-by-side.
