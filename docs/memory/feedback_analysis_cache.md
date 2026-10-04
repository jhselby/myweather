---
name: feedback-analysis-cache
description: All analysis scripts in analysis/ use a local cache (~/.cache/myweather/) via _cache.py. Never bypass it with a direct urlopen — that re-introduces the egress cost.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a8831ed-d0ae-48ad-9c90-349a29eadd94
---

When working in `analysis/` (or writing any new analysis/one-off script that touches `data.wymancove.com`), ALWAYS use the local cache module instead of `urllib.request.urlopen` directly.

**Pattern (in every analysis script):**
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

with open(cached_path(URL), "rb") as f:
    for raw in f: ...
```

The cache lives at `~/.cache/myweather/` (file per URL, named by basename). Default freshness window: 12 hours. Stale or missing files auto-redownload on the next call. Force a refresh with the env var `MYWEATHER_REFRESH=1` (one-shot) or by deleting the cached file.

**Why:** Every download of the 935 MB `forecast_error_log.jsonl` from `data.wymancove.com` costs ~$0.075 in GCS egress (peered to Cloudflare at $0.080/GB). Iterative work (fitting τ, tuning thresholds, evaluating regimes) had been doing 50-100 of those per month, contributing roughly half the cloud bill. The cache eliminates the repeated egress: first run downloads, every run after uses the local file at zero network cost. Documented in v0.6.104 (2026-06-16).

**How to apply:**
- When creating a NEW analysis script: import `cached_path` from the start. Don't use `urllib.request.urlopen` directly.
- When EDITING an existing analysis script: if you see `urllib.request.urlopen(req, ...)` reading from a `data.wymancove.com` URL, replace with `open(cached_path(URL), "rb")`. The Request object with custom User-Agent is no longer needed — `_cache.py` handles that.
- When running an analysis script that needs fresh data (e.g., R5 verification on its scheduled day): use `MYWEATHER_REFRESH=1 python3 analysis/<script>.py`, not a code change.
- When debugging "why is the cache stale?": `ls -la ~/.cache/myweather/` shows file mtimes; >12h triggers auto-refresh, otherwise the cache is intentional.
- When checking if a script needs patching: `grep "urllib.request.urlopen" analysis/*.py` should show only `analysis/_cache.py` itself.

**Don't:** add a one-off `urllib.urlopen` "just for this script" or to bypass the freshness window — both reintroduce the cost the cache exists to prevent. If freshness is the issue, use `MYWEATHER_REFRESH=1` or pass `refresh=True` to `cached_path()`.

**Ad-hoc probes count too.** When inspecting the pair log structure, sampling field ranges, counting per-day volume, or any other ONE-OFF diagnostic that touches `data.wymancove.com`, route through `cached_path` exactly the same way. Don't drop a raw `urllib.request.urlopen(...)` inline in a Bash heredoc just because "it's just one probe." On 2026-06-24 Joe caught me streaming the 70MB pair log twice that way (a per-day count + a cluster_spread range check) — both should have hit the cache. Same egress cost, same fix.

Related: [[project-gcs-soft-delete-trap]] (the storage-bytes half of the same June 2026 cost investigation), [[feedback-best-way-first]] (the meta — Joe wants the right architecture, not the cheap path).
