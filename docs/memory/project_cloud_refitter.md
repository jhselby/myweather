---
name: project-cloud-refitter
description: "Reference for myweather-refitter (live since 10-07): which runtime tables refit daily in the cloud, how the collector loads them, guards, state files, how to check a run, how to add a table. Ship-decision tables stay bundled."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-07T18:00:00.000Z
---

# Cloud refitter (live 10-07, v0.7.28 → v0.7.30)

**Why it exists:** Joe's rule — [[feedback_self_refit_tables_run_in_cloud]]. Before it, every "daily refit" table changed only when the Mac digest ran AND a collector deploy baked the JSON in.

## Moving parts
- **Function:** `myweather-refitter`, Cloud Functions gen2, us-east1, 8 GB / 2 vCPU / 1800 s, max-instances 1. Deploy: `make deploy-refitter`.
- **Schedule:** `myweather-refitter-schedule`, `30 4 * * *` America/New_York (04:30 ET — before the ~06:00 digest, after overnight rows close; time not critical, 30d windows + guards). Invoker SA `myweather-collector@`.
- **Code:** `refitter/main.py` (runner), `refitter/tables.py` (registry). Runs the unchanged `analysis/*` fitters (`call` a function or `argv` run as `__main__` via runpy, like the digest). `scikit-learn` in `requirements.txt` is for the learned-selector GBM.
- **Outputs in `gs://myweather-data/`:** `runtime_tables/<name>`, daily copy `runtime_tables/history/<YYYY-MM-DD>/<name>` (restore = copy back), streak histories `runtime_tables/state/<file>`, run status `runtime_tables/_status.json` (gzipped — read with `weather_collector.gcs_io.load_json`, not raw gsutil).
- **Collector side:** `weather_collector/runtime_tables.get(name, validate)` → GCS copy (generation re-checked every 600 s) → last-good in memory → bundled repo file. Log line `runtime_tables: <name> ← GCS (fitted <stamp>)`. The validator is the consumer's own `validate_*`, shared with the refitter guard.

## The 10 tables (in run order)
1. `l1_selector_table_curated` · 2. `l3_nbm_curated` · 3. `l4_nbm_curated` · 4. `lc_correction_table` · 5. `lc_recent_bias_gate` (state) · 6. `lsr_bias_table_curated` · 7. `sr_sea_breeze_lsr_curated` (stamp key `generated`) · 8. `chp_cell_gate` (stage2_vs_l6 → gate; state) · 9. `l1_selector_by_regime_walker` (by_regime → 3way → walker; state) · 10. `l1_learned_selector_curated` (v2 → v5 → curate; `LIVE_DEMOTED` in the curate script stays a ship decision).

## Guards
Structure (consumer validator) · stamp not older than previous · size: "ratio" (≥50% of previous rows) or "nonzero" (cell sets may shrink, never vanish) · row floors for selector (100k) / L3_NBM (100k) / L4_NBM (10k) · Lc: no field dropped. Refused or crashed → previous table put back on disk so later entries read the live copy; state not saved; reason in `_status.json` + ERROR log; `last_run_ok` False.

## NOT in the refitter (bundled, change only via ship)
- **Ship decisions:** skip tables, `APPLIED_CELLS`, `LIVE_DEMOTED`, and (Joe, 10-07) the frozen Stage 1/2 cell sets `ch_persistence_gate_curated`, `wd_persistence_gate_curated`, `wg_residual_persistence_curated`, `wg_l3_asymmetric_skip_curated`. Their tools write `analysis/output/candidates/` (`analysis/_candidates.py`). To ship a new set: copy candidate over the data file, bump, deploy.
- **Off/shadow layers:** c1 tables, cc combine, clp, dp/h residual persistence, blender, Lsr recent-bias gate, ws tables. Move one only if it goes live and is meant to self-refit.
- The Mac digest still rewrites bundled copies of the moved tables — fallback only; the GCS copies are authoritative.

## Adding a table
Consumer must read through `runtime_tables.get()` with a `validate_*` or the refit has no effect. Add a registry entry (steps, guard, summary, `state` if it keeps a history). Test with `REFITTER_DRY_RUN=1` in an rsync'd scratch copy of the repo — the fitters write history files in place.

## Check a run
`python -c "from weather_collector.gcs_io import load_json; import json; print(json.dumps(load_json('runtime_tables/_status.json'), indent=1))"` — every table `published: True`, `last_run_ok: True`. Then collector log for `← GCS` lines.

## Performance
Local dry run 108 s, peak RSS 1.9 GB; cloud ~7 min (cold `/tmp` cache adds ~1.2 GB → 8 GB memory). Collector first tick after moving to GCS loads: RSS +409..+536 MiB (watch).

Related: [[project_10_07_session]] · [[feedback_auto_curate_wholesale_overwrite]] · [[feedback_curated_json_daily_drift]]
