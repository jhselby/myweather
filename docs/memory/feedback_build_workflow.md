---
name: feedback-build-workflow
description: Correct version bump and build order for myweather PWA
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 263d9e31-8651-4d6d-a7fc-f90ef99692e0
---

Version lives in `index.html` (`id="appVersion"`). `build.py` reads it from there and writes `version.json`. Do NOT edit `version.json` directly — build.py will overwrite it.

**Why:** build.py extracts the version from the appVersion span in index.html and syncs version.json to match. Editing version.json first gets silently reverted.

**How to apply:** To bump version: edit the `<span id="appVersion">` in index.html, THEN run `python3 build.py`. Never the other way around.
