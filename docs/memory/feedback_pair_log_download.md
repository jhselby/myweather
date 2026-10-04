---
name: feedback_pair_log_download
description: analysis/_cache.py uses curl not urllib. urllib.request.urlopen stalls at ~40 MB on large Cloudflare-fronted composite GCS objects; caught 2026-07-17 hanging the digest 25 min.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 43be4b0e-1ee6-46ca-95b4-e8e62a53c216
---

`analysis/_cache.py` downloads via `subprocess.run(["curl", ...])`, not `urllib.request.urlopen`.

**Why:** `urllib.request.urlopen` stalls at ~40 MB on large Cloudflare-fronted composite GCS objects. The TCP connection stays ESTABLISHED but no bytes flow; the read hangs until the (very long) urlopen timeout. Caught 2026-07-17: the 2.5 GB `forecast_error_log.jsonl` (a `x-goog-component-count: 4` composite object) hung `anomaly_detector` for 25 min at the 40 MB mark with `.tmp` file untouched for 60+ seconds while the socket stayed open. `curl` handled the same fetch at ~24 MB/s (2.5 GB in 103 s). Same atomic `.tmp` → `os.replace(...)` pattern preserved; same `MYWEATHER_REFRESH=1` env-var honored.

**How to apply:**

- Any new analysis script that downloads from `data.wymancove.com` should use `_cache.cached_path(URL)` — never call `urllib.request.urlopen` directly.
- If diagnosing "the digest is hung," check `ps aux | grep analysis.` for a Python process holding an ESTABLISHED TCP connection to `172.67.218.50` (Cloudflare) with a growing but stalled `~/.cache/myweather/<file>.tmp`. Fix: kill the process, delete the `.tmp`, curl-download the file yourself to warm the cache, re-run the digest.
- Related — do NOT reintroduce retry-on-429 in the collector's Gemini path (unrelated to this cache but same "network error handling" family). See [[project_gemini_quota_real]].
