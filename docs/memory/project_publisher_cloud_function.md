---
name: publisher-cloud-function
description: "myweather-publisher Cloud Function (us-east1, gen2, 2GB, hourly cron) runs 6 dashboard-data publishers and pushes fresh JSON to GCS. Removes daily-manual-digest dependency for debug page freshness. Digest stays as-is for experiments."
metadata: 
  node_type: memory
  type: project
  originSessionId: d5b3b340-bcb5-4198-bf9b-651541917300
  modified: 2026-08-07T22:54:47.258Z
---

# myweather-publisher — hourly dashboard-data publisher

## Status: LIVE 2026-08-07 v0.6.395f

Cloud Function deployed to us-east1, gen2, Python 3.11, 2GB memory, 540s timeout, max-instances=1. Cloud Scheduler cron `0 * * * *` (America/New_York), first scheduled run 2026-08-07T23:00 EDT.

## What it publishes

Runs these 6 scripts (in order, each in its own try/except so one failure doesn't gate the others):

1. `mae_over_time.py` — the marquee output; debug page 24h/7d cells + accuracy-over-time chart depend on it.
2. `gate_firing_rollup.py`
3. `h_persistence_skill.py`
4. `h_pp_platt_calibration.py`
5. `h_pp_bin_calibration.py`
6. `pp_brier_reliability.py`

Skipped: `frontal_detector_test.py` (unit test, not a real publisher — grep-matched only).

Total runtime ~3–4 minutes per invocation. Cost ~0 (16% of Cloud Functions Gen2 free-tier compute budget at hourly cadence, in-region GCS reads free).

## Architecture

- `publisher/main.py` — Cloud Function entrypoint. Sets `MYWEATHER_CACHE_DIR=/tmp/cache`, `MYWEATHER_CACHE_MODE=gcs`, `MYWEATHER_OUTPUT_DIR=/tmp/output`. Imports each script and calls `.main()`.
- `analysis/_cache.py` — added `gcs` mode that reads pair log directly from `gs://myweather-data/` instead of curl-from-`data.wymancove.com`. 5-min TTL for warm-instance freshness.
- `analysis/_output.py` — new helper. Env-var override for output dir (`MYWEATHER_OUTPUT_DIR`). Local runs fall back to `analysis/output/` (unchanged behavior).
- Each of the 6 scripts modified to call `_output.out(name)` instead of `os.path.join(SCRIPT_DIR, "output", name)`. Same 3-line pattern each.
- `main.py` (top-level) lazy-imports both `run` and `publish` so the publisher container doesn't crash on missing collector secrets (GEMINI_API_KEY etc.).

## Makefile targets

- `make deploy-publisher` — deploys the Cloud Function.
- `make run-publisher` — manually fires the scheduler (for smoke tests).
- `make logs-publisher` — reads recent function logs.

## Auth setup

Cloud Scheduler uses OIDC service account `myweather-collector@weather-data-493811.iam.gserviceaccount.com` (same SA as the collector's scheduler). Granted `roles/run.invoker` on `myweather-publisher` at flip time.

## Debug page

Header shows `MAE data refreshed <MM-DD HH:MM ET>` via new `fmtET()` helper (v0.6.395h). Ticks forward hourly with each publisher run — the at-a-glance freshness check.

## Why this exists

Before this: `analysis/mae_over_time.py` (and 5 others) only ran when Joe manually invoked `analysis/runlog/run_digest.sh` on his Mac. If he didn't run it, the debug page silently rotted. Mac had to be on.

After: publishers run on Google's infra, hourly, unattended. Debug page always fresh. Digest stays for experiments (the h_* hypothesis scripts) — Joe still invokes it when he wants fresh verdicts. Digest is fully manual by design; publishers are fully automatic by design.

## Related

- [[feedback_curated_json_daily_drift]] — retires the "manual digest keeps page fresh" class of drift.
- [[project_todo]] — consistency sweep parked: other timestamps on the debug page (pp reliability drill-down, walkforward summary, Lc fit table) still use mixed formats. Not urgent.
