---
name: project-gcs-soft-delete-trap
description: GCS soft-delete is default-on at 7 days bucket-wide and silently bills for every overwritten version of every file — disable on any bucket the pipeline rewrites frequently
metadata: 
  node_type: memory
  type: project
  originSessionId: 43ac5ed4-a539-4e44-be37-7cbc5fe435f9
---

## The trap

Google Cloud Storage has a bucket-wide soft-delete policy that defaults to 7-day retention. Every object overwrite or delete leaves a "soft-deleted" version that occupies billable storage at the same rate as live data, for 7 days. The policy was rolled out as a default in late 2024 (post-UniSuper incident) and silently grandfathered onto existing buckets — `myweather-data`'s policy effective time was 2026-04-19, no opt-in.

## Why it's expensive for this pipeline

The collector and Fitter intentionally rewrite large log files repeatedly:
- `forecast_error_log.jsonl` — 4.14 GB, rewritten 2×/day by the Fitter for pruning
- `briefing_cache.json` — rewritten every 30 min
- `forecast_log.json`, `station_history.json`, others — frequent rewrites

Each rewrite mints a 7-day-billable ghost. By 2026-06-13 the bucket had **2.65 TB / 9,630 soft-deleted versions** sitting in limbo, costing ~$10/month against the visible 3.87 GB of live data. The Cloud Storage line on the billing report shows only the total — no breakdown distinguishing live storage from soft-deleted bloat. You'd only catch it by drilling into `gcloud storage ls --soft-deleted`.

**Why:** The default is sized for a data-lake workload where deletes are occasional. For our workload (frequent rewrites of large files), it's a silent multiplicative tax that scales with activity, not data volume.

## How to apply

- On any new GCS bucket the pipeline writes to, disable soft-delete immediately:
  ```
  gcloud storage buckets update gs://BUCKET --soft-delete-duration=0
  ```
- After disabling, purge existing soft-deleted versions to get immediate savings:
  ```
  gcloud storage rm --recursive --read-paths-from-stdin < <(gcloud storage ls --soft-deleted --recursive gs://BUCKET | grep '#')
  ```
- When the pipeline cost climbs unexpectedly, **check this first** before investigating compute or egress. Soft-delete bloat is invisible in the standard billing report and the default failure mode is silent accumulation.
- Cost audits should be a quarterly habit, not an emergency response. Defensive defaults at hyperscalers creep onto existing accounts without notification — the absence of a billing alert is not the same as the absence of a problem.

## Related

- [[project-correction-stack]] — Fitter rewrites of forecast_error_log.jsonl are the primary source of soft-deleted bloat in this project
