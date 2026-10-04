---
name: project-09-24-session
description: "09-24/25 Thu/Fri — 4 ships total. Morning: v0.7.1 (L4 add wg), v0.7.2 (L1 blender first APPLY flip, 3 dp cells). Afternoon/evening: v0.7.3 ROLLED BACK the v0.7.2 flip after discovering the GCS backstamped pair-log had been stale since Aug 21 — every fit from any backstamp-URL-only fitter (blender, per-obs classifier v0.6.644-6) since Aug 21 was on data ending Aug 20T20:07. See [[project_backstamp_stale_09_24]]."
metadata: 
  node_type: memory
  type: project
  originSessionId: c0c72043-9870-48db-8ece-306fd86fbedb
  modified: 2026-09-25T11:23:52.827Z
---

# 09-24 Thursday — three ships forward, one back

## Ships (4 commits — v0.7.3 rolls back v0.7.2)

- **3d92cd41 v0.7.1** — L4 add wg. Divergence 7/7 claim gate cleared; walkforward L4 wg +27.4%/+27.3% both views, 0 entangled. Backend-only.
- **ebfee3f4 analysis: l1_blender_retro_score** — new companion to shadow_verify. See [[project_l1_blender_retro_score]].
- **d7f242e3 v0.7.2** — L1 blender FIRST APPLY FLIP. `BLENDER_APPLIED_FIELDS = frozenset({"dp"})`. 3 dp curated cells serve blended forecasts.
- **b6149e53 v0.7.3** — **ROLLED BACK v0.7.2**. `BLENDER_APPLIED_FIELDS = frozenset()`. Same commit wires `analysis/nbm_backstamp_append.py` into publisher CF (incremental append via `bucket.compose()`, HWM sidecar at `gs://myweather-data/backstamp_hwm.json`). Adds `make backstamp-rebuild-and-upload` for manual full rebuild.
- **613bbb2d** — debug page updated to reflect v0.7.3 rollback + stale-fit audit finding in main blender tile.

## The rollback story (short — see [[project_backstamp_stale_09_24]] for full)

Investigating why the L1 blender shadow-verify tile showed 13 THIN → discovered `gs://myweather-data/forecast_error_log_backstamped.jsonl` was last-modified 2026-08-21, latest row `obs_time: 2026-08-20T20:07`. Five-week-frozen corpus. `nbm_backstamp.py` runs manually on Joe's Mac and had been uploaded to GCS exactly once, then never again. Anything reading the backstamp-only URL via `cached_path()` had been fitting on a file that ends Aug 20.

Two consequences shipped:
1. **The plumbing fix** — `nbm_backstamp_append.py` in the publisher CF: reads live pair-log HWM byte offset, range-downloads new bytes, `bucket.compose()` appends. Zero NBM blob downloads (post-Aug-19 rows already have `error_l3_nbm` from live). Runs in <30s per tick. Manual rebuild target via Makefile.
2. **The rollback + audit** — refit `l1_blender_stage1.py` on fresh data: 11 of 13 shipped cells fail halves-stable, including all 3 dp cells the v0.7.2 flip promoted. `BLENDER_APPLIED_FIELDS` reset to empty. `l1_blender_curated.json` intentionally NOT re-curated in v0.7.3 (deferred — since applied-fields empty, no cell fires and shadow telemetry now accumulates on fresh data).

## Refit results — blender + classifier on fresh data

**Blender (`l1_blender_stage1.py`):** 2 of 13 shipped cells survive halves-stable:
- `h/pre_frontal/24-47h` (A+25.7% / B+8.1%, ω̄ 0.44-0.55)
- `t/se_flow/24-47h` (A+11.8% / B+14.9%, ω̄ 0.37-0.46)
One NEW candidate not in shipped set: `wg/pre_frontal/12-23`. All other cells drop to one-window / UNSTABLE.

**Per-obs classifier v2b linear (v0.6.644-6):** STAGE 1 HOLD on both h and t with every cell degenerate (fNBM 67-99% — rubber-stamps NBM, no per-obs selection).

**Non-linear GBM experiment (new v3/v4 built this session):** v3 single-split showed 20+ PROMOTE cells across h, ch, wg, sr, cc. v4 halves-stable narrows to **9 sr cells + 1 ch cell** — see [[project_l1_per_obs_gbm_experiment]]. sr is a real physically-coherent unlock (non-linear cloud/sun-angle interactions); other fields' apparent wins were single-window artifacts.

## Diagnostic-driven chain

Digest triage (pre-rollback, still valid):
- `chp_nbm: DROP ch` — THIN artifact, no action.
- `sr.l5_nbm HOT +22.7%` — dead layer, autumn-equinox real-shift, heals when window rolls.
- `l2_lead_decay_fit` info→promote pr τ=6h — noise-adjacent thrash, HOLD.
- `l1_blender_shadow_verify` all THIN — this is what unspooled the whole session.

## v0.7.2 mechanics (retained; still the shape v0.7.3 uses)

`BLENDER_APPLIED_FIELDS = frozenset()` in `weather_collector/processors/l1_selector.py`. Consumers gate on `if f in _BLENDER_APPLIED_FIELDS and _blend_shadow_v is not None`. Adding cells later is one-line. `blender_omega()` still runs for shadow telemetry regardless of allowlist. `frozenset({"dp"})` was the aborted v0.7.2 state.

## Strategic re-read

Was headed toward "blender is the path forward, selector is plateaued." Not what the fresh data supports. See [[project_l1_per_obs_gbm_experiment]] for the honest picture: sr non-linear per-obs is the real remaining lever (~9 cells, physically justified). Blender is a narrow 2-3-cell specialist. Everything else is diminishing-returns grind.

## Follow-ups

- v5 per-obs classifier scored vs `error_prod_real` (not `error_l4`) to get honest ship-gain over the current selector's baseline. Necessary before shipping sr cells.
- Re-curate `l1_blender_curated.json` to the 2-3 real STABLE cells once one week of fresh-data shadow accumulates.
- Audit all other backstamp-URL-only fitters and re-run on fresh data: `h_l1_selector_ims_stage0.py`, `h_l1_selector_ims_stage1.py`, `h_l1_selector_multiaxis_stage1.py`, `simpson_guard_shadow.py`, `l1_blender_shadow_verify.py` (this last is in publisher CF and now auto-corrects).
- 09-26 gate for h per-obs axes (per [[project_l1_selector_per_obs_axes]]) is affected — that fitter is on the stale-URL list.
