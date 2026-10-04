---
name: pwa-hosting
description: PWA HTML is served via GitHub Pages at wymancove.com directly from the main branch of the repo
metadata: 
  node_type: memory
  type: project
  originSessionId: b64b54ae-d13f-48c0-b164-388979caa9c3
---

The PWA (`index.html` + `js/*.js` + `styles/*.css` + any sibling HTML like `decay_debug.html`) is served by **GitHub Pages** at `https://wymancove.com/` directly from the `main` branch. A `git push` to main is the deploy — usually live within ~30s.

**Why:** No build step beyond `build.py` cache-busting; static repo serves directly.

**How to apply:**
- After `git push`, the change is live at `wymancove.com/<file>` almost immediately. No separate deploy step for frontend.
- This is distinct from the *collector*, which is on Google Cloud Functions and requires `make deploy-collector`.
- Data files (`weather_data.json`, `forecast_log.json`, `decay_corrections.json`, etc.) are NOT served by Pages — they're at `data.wymancove.com` (Cloudflare in front of the GCS bucket `myweather-data`).
- GitHub *Actions* is still dead (CLAUDE.md §9). GitHub *Pages* is the live serving mechanism. Don't confuse them.
