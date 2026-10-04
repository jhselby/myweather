---
name: project-backstamp-stale-09-24
description: "09-24 root-cause + fix: GCS forecast_error_log_backstamped.jsonl had been frozen since 2026-08-21 (5 weeks). Every fitter reading the backstamp-only URL via cached_path() saw data ending 2026-08-20T20:07. Fixed with nbm_backstamp_append.py in publisher CF (bucket.compose + byte-offset HWM). Also caused the v0.7.2 → v0.7.3 blender rollback."
metadata: 
  node_type: memory
  type: project
  originSessionId: 12ef5cc5-cd7f-4340-9a6f-4df528b5b372
  modified: 2026-09-25T11:24:31.511Z
---

# Backstamp stale-corpus incident + fix — 09-24

## What broke

`gs://myweather-data/forecast_error_log_backstamped.jsonl` — the enriched pair-log that carries `raw_nbm / l2_nbm / l3_nbm / l4_nbm` stamps for historical rows — was last-modified 2026-08-21. Latest `obs_time` in the file: `2026-08-20T20:07`. **Frozen for 5 weeks** and nobody caught it.

## Root cause

`analysis/nbm_backstamp.py` is a manual local script. It writes to `~/.cache/myweather_nbm_backstamp/forecast_error_log_backstamped.jsonl`. Nothing in the repo — not `publisher/main.py`, not Makefile, not any scheduler — uploads it to GCS. It got `gsutil cp`'d up manually once on Aug 21 and never again.

## Discovery path (the diagnostic chain)

1. Opened debug page L1 blender shadow tile → 13 THIN cells.
2. Checked `l1_blender_shadow_verify.py` — reads `PAIR_URL = data.wymancove.com/forecast_error_log_backstamped.jsonl`, looks for `blend_shadow` field. Blender was writing to live pair-log since 09-23.
3. `curl -sI` on the URL: last-modified Aug 21, latest row obs_time Aug 20.
4. Traced upstream to `nbm_backstamp.py` (manual local, no cloud path).

## The fix (shipped v0.7.3)

New `analysis/nbm_backstamp_append.py`, wired FIRST in publisher CF's job list. Every hour:
1. Read `gs://myweather-data/backstamp_hwm.json` for `{offset, last_obs_time}` byte-offset high-water mark. If missing, seed from tail of backstamped file.
2. `bucket.blob("forecast_error_log.jsonl").reload()` → get current pair-log size.
3. Range-download bytes `[hwm_offset .. size]`.
4. Parse rows; post-Aug-19 rows already carry `error_l3_nbm` (live-stamped). Just pass through and fill `error_l4_nbm` counterfactual via `_maybe_add_l4_nbm()` (shared with `nbm_backstamp.py`).
5. Upload delta as `backstamp_delta.jsonl`. `main_blob.compose([main_blob, delta_blob])` — GCS native atomic append. Delete delta. Patch cache-control to `no-cache`.
6. Update HWM to new offset + newest `obs_time`.

Zero NBM blob downloads. Runs in <30s per tick. Publisher CF has 540s / 2GB — plenty of headroom.

## Manual escape hatch

`make backstamp-rebuild-and-upload` — full local rebuild via `nbm_backstamp`, gsutil upload, `--reset-hwm` so next appender tick reseeds. Needed when the L4_NBM curated table changes (invalidates the counterfactual L4_NBM stamps on historical rows).

## Debug/logging note

Publisher CF's `logging.info` calls are dropped below WARNING severity — invisible in gcloud logs. Only `logging.error` shows. `print(..., flush=True)` works. Same trap as v0.6.621. Every diagnostic line in `nbm_backstamp_append.main()` uses `print(..., flush=True)`.

## Off-by-one caught + fixed

First deploy: `_seed_hwm()` set `offset = 516,713,041` when file size was 516,713,040. Cause: `data.split(b"\n")` produces a trailing empty element past the final `\n`; loop added `len(line)+1 = 1` for it. Fix: `offset = min(offset, pb.size)` cap at file size.

## Fitter-freshness audit (which shipped work was on stale data?)

**SAFE (read `pair_log_paths()` = live + backstamp, so live carries recent data):**
- `l3_nbm_fit.py`, `l3_nbm_fit_by_regime.py` → `l3_nbm_curated.json`
- `l4_nbm_fit.py` → `l4_nbm_curated.json`
- `l1_selector_fit_by_regime.py` → `l1_selector_by_regime_walker.json`
- `nbm_skip_add_audit.py`, `nbm_skip_earning_audit.py` → `skip_table_nbm_curated.json`
- `nbm_walkforward_validator.py`

All ships since 08-21 touching these JSONs (v0.6.581, .584, .586, .588, .602, .609, .613, .622, .635-637, .647) are fine.

**SUSPECT (read `cached_path(PAIR_LOG_BACKSTAMP_URL)` — backstamp-only, stale):**
- `l1_blender_stage1.py` → `l1_blender_curated.json` (v0.7.0 shadow, v0.7.2 apply flip — BOTH stale-fit, v0.7.3 rolled back)
- `l1_selector_per_obs_classifier_stage1.py` → `l1_learned_selector_curated.json` (v0.6.644, shadow-only)
- `l1_selector_per_obs_classifier_stage1_v2.py` (same output family, v0.6.646, shadow-only)
- `h_l1_selector_ims_stage0.py`, `h_l1_selector_ims_stage1.py`, `h_l1_selector_multiaxis_stage1.py` (v0.6.640 shadow ims rule, 09-26 flip watch — those numbers were on stale data)
- `simpson_guard_shadow.py` (shadow-only, verdict on stale data)
- `l1_blender_shadow_verify.py` (publisher CF — auto-corrects now)

## Cache location gotcha

Two DIFFERENT local caches involved:
- `~/.cache/myweather_nbm_backstamp/forecast_error_log_backstamped.jsonl` — output of `nbm_backstamp.py`. Freshly rebuilt on Joe's Mac 09-24 08:03.
- `~/.cache/myweather/forecast_error_log_backstamped.jsonl` — `cached_path()` curl-mirror of the GCS URL. This is what fitters actually READ. Was last curled 09-24 07:56 — from the STALE GCS file. Contents ended 2026-08-20T20:07.

The fitters do NOT read the local `nbm_backstamp` cache. They read the GCS mirror. So even though Joe's local backstamp was fresh 08:03, every fit that morning still ran on Aug-20-ending data.

## Related feedback memories

- [[feedback_backstamp_url_semantic_trap]] — check `pair_log_paths()` vs `cached_path(BACKSTAMP_URL)` BEFORE trusting a fitter result
- [[feedback_shipped_on_stale_needs_refit]] — anything shipped from a backstamp-URL-only fitter needs periodic refit-on-fresh sanity check
