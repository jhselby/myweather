---
name: project-collector-memory-leak-hunt
description: "Nightly OOM on myweather-collector Cloud Function — memory bumped 8/11, RSS logging deployed, read results 8/12+"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2f50593b-82c2-4b32-8882-35cd1d4218c7
  modified: 2026-08-15T10:23:08.472Z
---

Nightly `[ALERT] Error executions > 0` emails on myweather-collector.

**Root cause found 2026-08-11:** OOM kill — 1499 MiB used against 1464 MiB effective limit. Once per night, ~05:27 UTC. Warm container drifts up over ~24h until it tips past the limit on some tick.

**Acute fix shipped 2026-08-11:** Memory bumped 1536MB → 2048MB in Makefile deploy-collector target. Cost delta ~$0.30/mo. Should silence the alert immediately.

**Leak-hunt instrumentation shipped 2026-08-11:** `weather_collector/collector.py:main()` now logs one `MEMPROBE start_rss_mib=... end_rss_mib=... delta_mib=... elapsed_s=...` line per tick via `resource.getrusage(RUSAGE_SELF).ru_maxrss` (Linux kb / macOS bytes auto-detect in `_rss_mib()`).

**2026-08-15 REAL FIX — the 08-11 ship was a silent no-op.** Grepped Cloud Logging for `MEMPROBE` over a 5-day freshness window: zero hits. Even the `logging.info("Wyman Cove Weather...")` banner from `main()` had zero hits. Root cause: no `logging.basicConfig()` anywhere in the codebase → Python root logger defaults to WARNING → every `logging.info(...)` silently dropped by Cloud Run. Fix shipped v0.6.414 (10:22:40 UTC): both MEMPROBE lines converted to `print(..., flush=True)` — prints go straight to stderr → Cloud Logging. First real MEMPROBE line expected on ~10:27 UTC tick. Data collection restart date effectively 2026-08-15, not 2026-08-11.

**How to apply (revised):** wait 24h from 2026-08-15 for a real dataset. Same interpretation rubric below still valid.

**Why:** need real data before guessing which processor holds memory across ticks. Module-level state I already ruled out: `_TICK_BUFFER` (drained each tick), `_ASYMMETRIC_CACHE` (bounded ~7 entries), `_TABLE_CACHE = None` singletons (one-shot lazy loads). Leak is probably in a library (google-cloud-storage client, aiohttp session not closed) OR a fetcher's growing structure I didn't find OR Python allocator not returning to OS.

**How to apply:** on 2026-08-12 or later (need ~24h / 144 ticks of data), read the probes:
```
gcloud functions logs read myweather-collector --region=us-east1 --gen2 --limit=500 | grep MEMPROBE
```
Interpretation:
- `start_rss_mib` climbing across ticks on same instance → real leak; `delta_mib` per tick shows which invocations add.
- `start_rss_mib` resets on new instance, climbs within its life → confirmed slow leak.
- `start_rss_mib` flat, one huge `delta_mib` on specific ticks → not a leak; one heavy job (Fitter, Gemini briefing) tips over.

Nudge Joe to check within a few days. If confirmed leak, next step is checkpoint-based memory probes inside `main()` to localize which processor adds it.

Related: [[project_publisher_cloud_function]] (sibling function, same runtime, unaffected so far).
