---
name: project-l1-blender-stale-fit-audit
description: "09-24 refit of l1_blender_stage1.py on fresh data. 11 of 13 shipped v0.7.0 curated cells fail halves-stable. Survivors: h/pre_frontal/24-47 and t/se_flow/24-47. New candidate not in shipped set: wg/pre_frontal/12-23. Caused v0.7.3 rollback of the v0.7.2 dp APPLY flip. l1_blender_curated.json NOT re-curated in v0.7.3 — deferred until 7d fresh-data shadow accumulates."
metadata: 
  node_type: memory
  type: project
  originSessionId: 12ef5cc5-cd7f-4340-9a6f-4df528b5b372
  modified: 2026-09-25T11:26:11.218Z
---

# L1 blender stale-fit audit — 09-24

## Origin

Refit `analysis/l1_blender_stage1.py` on fresh data after discovering the GCS backstamped file had been frozen since Aug 21 (see [[project_backstamp_stale_09_24]]). Sweep all 5 fields that shipped v0.7.0 STABLE cells (dp, h, ch, wg, t).

## Cell-by-cell verdict — shipped 13 vs fresh refit

| Field | Cell | v0.7.0 (stale) | Fresh refit | Live in v0.7.2 apply flip? |
|---|---|---|---|---|
| dp | nw_flow/12-23 | STABLE | one-window | **YES → rolled back** |
| dp | sw_flow/12-23 | STABLE | UNSTABLE | **YES → rolled back** |
| dp | sw_flow/24-47 | STABLE | one-window | **YES → rolled back** |
| h | nw_flow/24-47 | STABLE | dropped (n insufficient) | no |
| h | pre_frontal/12-23 | STABLE | one-window | no |
| **h** | **pre_frontal/24-47** | **STABLE** | **STABLE ✓** (A+25.7% / B+8.1%, ω̄ 0.44-0.55) | no |
| h | se_flow/12-23 | STABLE | UNSTABLE | no |
| ch | nw_flow/12-23 | STABLE | UNSTABLE | no |
| ch | sw_flow/12-23 | STABLE | UNSTABLE | no |
| wg | nw_flow/0-5 | STABLE | one-window | no |
| t | se_flow/12-23 | STABLE | UNSTABLE | no |
| **t** | **se_flow/24-47** | **STABLE** | **STABLE ✓** (A+11.8% / B+14.9%, ω̄ 0.37-0.46) | no |
| t | sea_breeze/24-47 | STABLE | dropped (n insufficient) | no |

**Survivors: 2 of 13.** All 3 dp cells that were LIVE in v0.7.2 fail on fresh data.

## New candidate not in shipped set

**wg/pre_frontal/12-23** emerges as STABLE on fresh data (A+5.0% / B+3.5%, ω̄ 0.34-0.46). Modest lift but halves-stable, non-degenerate. Would be added to any re-curated set.

## v0.7.3 disposition

- `BLENDER_APPLIED_FIELDS = frozenset()` — pure shadow.
- `l1_blender_curated.json` intentionally NOT modified. Reasoning: since applied-fields is empty, no cell fires regardless of the curated table's contents. Better to leave the stale 13 cells in place, let shadow-verify (now on fresh data via [[project_backstamp_stale_09_24]] appender) accumulate real 7d/30d numbers over the next week, then re-curate from that empirical evidence rather than the halves-stable stage1 numbers alone.
- Blender infrastructure (ω computation, blend_shadow stamping, shadow-verify tile) stays fully live.

## Related

- [[project_backstamp_stale_09_24]] — root cause + fix (nbm_backstamp_append.py in publisher CF)
- [[project_l1_per_obs_gbm_experiment]] — parallel finding: non-linear per-obs classifier reveals real signal on sr (9 cells halves-stable) that linear v2b missed; blender's 2 survivors and classifier's sr cells stack (different fields)
- [[project_l1_blender_retro_score]] — retro-score tool (built 09-24) itself unaffected by the audit; it just reconstructs ω on any row, doesn't fit new cells

## Next actions

1. Let shadow-verify accumulate 7d on fresh data (post-2026-09-24 16:00 UTC).
2. Re-run stage1 in a week; STABLE set should stabilize.
3. Re-curate `l1_blender_curated.json` to the 2-3 real cells + wg/pre_frontal/12-23.
4. Consider flipping the 2 survivors into `BLENDER_APPLIED_FIELDS` cell-membership (not field-membership — need finer granularity than the current frozenset since only some cells within each field pass).
