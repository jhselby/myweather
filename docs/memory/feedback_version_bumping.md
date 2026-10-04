---
name: feedback-version-bumping
description: Always bump version on every push; use a/b/c suffixes for minor changes
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f73ef82b-b9fa-4a7b-b4ac-3975805e79b2
---

Bump the version in index.html on every single push to GitHub, no exceptions. Use a/b/c suffixes (e.g. v0.5.174a, v0.5.174b) for minor changes within the same feature so Joe can always confirm what's live in the browser.

**Why:** Without a version bump, Joe can't tell if he's looking at the new code or a cached version.

**How to apply:** Before every `git commit && git push`, bump the version. If the change is minor (analytics swap, wording fix, config tweak), use a letter suffix rather than incrementing the number.
