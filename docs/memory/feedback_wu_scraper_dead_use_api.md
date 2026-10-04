---
name: wu-scraper-dead-use-api
description: WU browser-page scraping fails from GCP IPs; use the PWS observations API with the existing WU_API_KEY env var instead
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c00612bd-49b6-498e-9bf3-3707c2c1cd1e
  modified: 2026-09-17T15:33:47.755Z
---

WU (wunderground.com) is an Angular SPA. Its pre-rendered HTML is inconsistent from Cloud Function egress IPs — the browser-page scraper fails every run (verified 38/38 fails 09-17). Do not try scraping fixes, headers, retries, or user-agent tweaks.

**Rule:** any WU data (single PWS or multi-station) goes through the API at `https://api.weather.com/v2/pws/observations/...` using `os.environ["WU_API_KEY"]`. That key is already provisioned in the collector Cloud Function and works — the 31-station wind-blend fetcher (`wu_scraper_realtime.get_current_observation`) uses it every 10 min.

**Why:** shipped in v0.6.639 after the Castle Hill scraper broke silently for days. Endpoint choice: `/current` for a live single reading (returns `imperial.temp`), `/all/1day` for the day-so-far aggregate (returns `imperial.tempAvg`). Don't confuse them.

**How to apply:** when a WU-sourced fetch starts failing, do not debug the DOM. Rewrite to the API. Joe has a free key that permits both endpoints without owning a PWS.
