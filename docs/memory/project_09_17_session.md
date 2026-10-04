---
name: project-09-17-session
description: "09-17 session — 1 ship (v0.6.639 PWS-via-API); t \"crash\" was two unrelated things (thin-window artifact + PWS ingest failure)"
metadata: 
  node_type: memory
  type: project
  originSessionId: c00612bd-49b6-498e-9bf3-3707c2c1cd1e
  modified: 2026-09-17T15:34:15.006Z
---

**1 ship: v0.6.639** — Castle Hill PWS rewritten from WU browser-page scrape to the WU PWS observations API (`/current` endpoint, existing `WU_API_KEY`). Scraper had failed 38/38 runs; post-deploy `sources.pws.status` flipped error → ok at 15:17 UTC.

**"t is crashing" turned out to be two unrelated things, both non-actionable:**

1. **PWS ingest failure** (the log-spam side): WU Angular SPA served inconsistent HTML from GCP IPs. Not a data-quality issue — PWS is fallback-of-fallback at `hyperlocal.py:391`, never in prod path when WU multi-station is ok. Fixed by v0.6.639. See [[feedback_wu_scraper_dead_use_api]].

2. **12h t value_captured = -1002% (later -208%)**: real short-lead t chooser slippage today. per_field_scoring.json → windows.12h.per_field.t: prod_mae 1.743 vs best_public 1.622; 6-11h band -90% lift; chooser_vs_prod -39%. BUT — 12h window has 8h pair-log backstamp lag, per-band n=48, page itself flags n≤50 as noise. Value_captured is a magnifying ratio (captured/oracle_gain); small oracle gaps make chooser slips explode. -1002 → -208 between refreshes is exactly that noise. No ship. Wait for 24h to catch up.

**Also this session:**
- Morning t FRESH FIRE remains lucky-baseline artifact per [[feedback_fresh_fire_lucky_baseline_artifact]] — self-heals ~09-21.
- `condition_source` mislabel documented: [[feedback_condition_source_is_wind_not_temp]] (it's wind, not temp).

**How to apply:** if t 12h value_captured fires again alone at thin n, don't chase. If 24h/7d follow, then investigate.
