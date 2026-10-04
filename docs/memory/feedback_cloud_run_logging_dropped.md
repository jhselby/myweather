---
name: cloud-run-logging-dropped
description: "In the myweather Cloud Function collector, `logging.info(...)` is silently dropped — root logger sits at WARNING with no basicConfig. Use `print(..., flush=True)` for anything meant to reach `gcloud functions logs read`. This trap has hit twice now (2026-08-15 MEMPROBE; 2026-09-14 frontal detector v0.6.620)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ece03753-be53-47fd-b95c-6a699b0574ab
  modified: 2026-09-14T18:46:19.171Z
---

# Rule

In `weather_collector/*` code deployed to Google Cloud Functions gen2 (the myweather-collector), **`logging.info(...)` is silently dropped**. Use `print(msg, flush=True)` instead.

**Why:** No `basicConfig(level=INFO)` is set anywhere in the collector, so Python's root logger defaults to WARNING. INFO-level records never reach stdout, so Cloud Logging captures nothing. The `flush=True` matters because Cloud Functions buffers stdout aggressively — an unflushed `print` may not appear before the function returns.

**How to apply:**
- Any new diagnostic/observability line in `weather_collector/**/*.py` uses `print(msg, flush=True)`, not `logging.info(...)`.
- If you inherit code that already uses `logging.info`, look for a companion comment (`collector.py:495` has one from the 2026-08-15 MEMPROBE incident) — if none, the line is probably dead in prod.
- `logging.warning`, `logging.error`, `logging.critical` work fine and go to Cloud Logging with the right severity — use those for actual warnings/errors.
- Before deploying a new diagnostic, verify it lands: deploy, wait one collector tick, `gcloud functions logs read myweather-collector --region=us-east1 --gen2 --limit=30 | grep <marker>`. Zero output = trap hit.

**Two incidents so far:**
1. 2026-08-15 v0.6.414 — MEMPROBE `logging.info` produced nothing; fixed to `print(..., flush=True)`; comment left at `collector.py:495`.
2. 2026-09-14 v0.6.620/621 — frontal detector diagnostic `logging.info` produced nothing across three post-deploy ticks; fixed in v0.6.621. Should have caught by reading the `collector.py:495` comment before adding the log line.

**Meta-lesson:** in-repo comments encode hard-won operational knowledge. Before adding a new log call, grep for `silently dropped` or `basicConfig` in the target module. Two minutes of prophylaxis beats one revert + redeploy.

## Related

- [[project_frontal_detector_health_09_14]] — the v0.6.621 incident.
- [[feedback_verify_writers_for_read_paths]] — sibling: verify diagnostic outputs actually land in the store they claim to write to.
- `weather_collector/collector.py:495` — the original MEMPROBE fix comment that documented this trap.
