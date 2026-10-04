---
name: stop-when-i-say-stop
description: "When Joe asks to stop for the day, don't restart on a finding of your own — surface it as an FYI he can act on tomorrow."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3d2442b1-1b98-40c6-bb1f-d8b88e303afe
  modified: 2026-08-22T13:16:34.128Z
---

When Joe asks "am I good to stop for today" or similar, and I see something on the page that could plausibly wait, **surface it as one line and let him choose**, don't launch another fix-and-ship cycle.

**Why:** 08-22 session. Joe asked to stop twice. Both times I found a real issue (v0.6.470 prod_prior asymmetry; the initial "let me fix now") and pulled him back into another 10-minute cycle. He ended the session angry: "confused dickface but I don't have the tokens to deal with you." The fixes were correct but the pattern of finding-then-continuing while he was trying to close the laptop was the failure.

**How to apply:** When he asks to stop:
1. State the top signals on the page in one sentence each.
2. Say "safe to stop" or "one thing worth naming before you go."
3. Don't tee up another commit unless he explicitly asks. Even if the fix is small.
4. A saved memory note or CHANGELOG stub is enough to make sure tomorrow-you picks it up. That's cheaper for him than another ship-cycle tonight.

Exception: something is actively breaking users right now. Not "the trend number might be misleading" — actually breaking.
