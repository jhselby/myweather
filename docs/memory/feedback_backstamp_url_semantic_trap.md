---
name: feedback-backstamp-url-semantic-trap
description: "Fitters in analysis/ split into two freshness classes: those reading pair_log_paths() (live pair-log + backstamped, always covers current data) and those reading cached_path(PAIR_LOG_BACKSTAMP_URL) directly (backstamp file only, freshness depends entirely on last backstamp upload). Silently different. Check WHICH before trusting any fitter result."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 12ef5cc5-cd7f-4340-9a6f-4df528b5b372
  modified: 2026-09-25T11:25:41.949Z
---

# Backstamp URL semantic trap

Analysis fitters in `analysis/*.py` fall into two categories with silently very different data freshness properties:

**Category A — SAFE (reads live + backstamp):**
```python
from analysis._cache import pair_log_paths
for path in pair_log_paths():
    for line in open(path): ...
```
Iterates BOTH the live pair-log (updated by collector every 10 min) AND the backstamped file. Recent data always covered by the live pair-log even if backstamp is stale.

**Category B — SUSPECT (backstamp-only):**
```python
from _cache import cached_path
PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
with open(cached_path(PAIR_URL)) as fh: ...
```
Reads ONLY the backstamped file. Freshness = whenever the GCS backstamped file was last updated. Since 2026-09-24 an incremental appender runs in publisher CF (see [[project_backstamp_stale_09_24]]); before that, it depended on Joe manually running `nbm_backstamp` locally and uploading.

## Why: Before trusting any fitter's output, especially "shadow" work not yet in production, check which URL pattern it uses. Category B fitters can silently regress to a frozen window without any error signal — the file is present, cached_path succeeds, iteration completes, cells fit, verdict prints. Every step looks normal.

## How to apply: When reviewing/interpreting/shipping from a Category-B fitter's output:
1. Grep the fitter: `grep -n "pair_log_paths\|PAIR_URL\|cached_path" analysis/that_fitter.py`
2. If it's Category B, check the GCS file freshness: `gsutil ls -l gs://myweather-data/forecast_error_log_backstamped.jsonl` — if last-modified > 24h old, results are on stale data.
3. If stale, purge local cache (`rm ~/.cache/myweather/forecast_error_log_backstamped.jsonl`) and re-fit before believing any number.

## Known Category B fitters (as of 09-24)

- `l1_blender_stage1.py`
- `l1_blender_shadow_verify.py`
- `l1_selector_per_obs_classifier_stage1.py`
- `l1_selector_per_obs_classifier_stage1_v2.py`
- `l1_selector_per_obs_classifier_stage1_v3.py` (new 09-24)
- `l1_selector_per_obs_classifier_stage1_v4.py` (new 09-24)
- `h_l1_selector_ims_stage0.py`, `h_l1_selector_ims_stage1.py`, `h_l1_selector_multiaxis_stage1.py`
- `simpson_guard_shadow.py`
- `l1_blender_retro_score.py`

Ideally all Category B fitters would migrate to `pair_log_paths()` since post-Aug-19 rows in the live pair-log already carry `error_l3_nbm`. The backstamp-only URL exists because pre-Aug-19 rows need the NBM backfill stamping — but for cells with sufficient recent-only data, live-only is fine.
