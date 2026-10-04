---
name: feedback-nbm-point-dual-deploy
description: "When touching weather_collector/fetchers/nbm_point.py, remind Joe to deploy nbm-ingester (and nbm-backfill if used) in addition to the collector. Joe doesn't watch nbm-ingester and won't remember on his own."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 227534a4-3adc-4478-8c5a-548a1c627fe8
  modified: 2026-08-27T15:31:14.668Z
---

When any change touches `weather_collector/fetchers/nbm_point.py` (FIELD_SPECS, `_plan_ranges`, `fetch_nbm_lead`, or anything else the module exports), **remind Joe to deploy `nbm-ingester` in addition to the collector**. If the change would also affect historical backfill runs, add `nbm-backfill` to the reminder.

**Why:** `nbm-ingester` is a separate Cloud Function (created 2026-08-18) that Joe doesn't watch — it has no debug-page footprint, doesn't write `weather_data.json`, and only surfaces as a sidecar file (`nbm_point_extract.json`) that the collector reads. If the collector-side code is updated but the ingester isn't redeployed, the sidecar keeps getting written with the OLD field list and any new NBM fields silently never populate. Joe found this out on 08-27 during the TSTM+APCP ship (v0.6.512) and said explicitly "you'll remind me and I'll do it."

**How to apply:** In the ship summary for any change to `nbm_point.py`, list the deploys explicitly:
- `make deploy-collector`
- `make deploy-nbm-ingester`
- `make deploy-nbm-backfill` (only if backfill logic is affected)

Don't assume Joe remembers the ingester is separate — call it out every time. Related: [[project_nbm_parallel_pipeline_plan.md]] for the ingester's role in the NBM cascade.
