---
name: feedback-ios-touch-testing
description: "Always test iOS touch behavior locally before pushing to live site; transparent backdrops don't intercept touches on iOS Safari"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3dfa035b-2292-4347-a3d2-a1c8e3b2dcf4
---

Never push iOS touch fixes directly to the live site without local testing first. Broke the live app 3 times in one session.

**Why:** iOS Safari has non-obvious touch handling differences from desktop — transparent divs don't intercept touches, bare divs without onclick attributes don't fire click events, etc. Each attempted fix broke something new.

**How to apply:** For any change that affects touch/click event handling:
1. Implement the fix locally
2. Have Joe test via `http://[Mac-IP]:8000` on iOS Safari (get IP with `ipconfig getifaddr en0`)
3. Only push after confirmed working

**The working fix for card backdrop:** Use document-level capture-phase listeners (`touchstart` non-passive + `click`) instead of listeners on the backdrop div. Capture phase fires before anything else on iOS regardless of element transparency or z-index. Store handler on `window.__cardOutsideHandler` for cleanup.

**Why transparent backdrops fail on iOS:** iOS Safari skips transparent elements during hit-testing, so taps fall through to whatever card is behind the backdrop. That card's onclick fires and opens it.
