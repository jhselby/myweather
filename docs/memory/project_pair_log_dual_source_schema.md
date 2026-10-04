---
name: pair-log-dual-source-schema
description: "Phase 0 (2026-08-18) design lock: pair-log schema extension for option-1 parallel HRRR/NBM cascades. Existing forecast_lN / error_lN columns keep HRRR semantics unchanged (forward-only migration). New forecast_lN_nbm / error_lN_nbm columns added per (field, layer). New pick_source column names the selector's choice. Legacy rows get null on the new columns and age out naturally over the 30-day retention window."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0f119ecf-9735-4bab-add3-866c32f13465
  modified: 2026-08-18T23:04:07.599Z
---

# Pair-log schema extension for parallel HRRR/NBM cascades

## Decision (Phase 0, 2026-08-18)

The pair-log (`forecast_error_log.jsonl` in GCS) extends **forward-only**:

- Existing `forecast_lN` / `error_lN` columns keep their meaning: HRRR
  pipeline. Since production has always run against HRRR-source Open-Meteo,
  this is not a rename — same data.
- New columns per (field, layer): `forecast_lN_nbm`, `error_lN_nbm`.
- New scalar: `pick_source` ∈ {"hrrr", "nbm"} — the source whose L6 output
  was routed to the user for this (field, run, lead) triple.
- Top-level `forecast` / `error` / `applied_layer` continue to reflect the
  **user-facing** value (== the picked source's applied layer). No change
  in semantics for consumers already reading these.

## Layer coverage per source

| Layer | HRRR | NBM (per field)                                 |
|-------|------|-------------------------------------------------|
| l1    | ✓    | ✓ where NBM emits raw (see below)               |
| l2    | ✓    | ✓ (per-source Kalman state, cold-start settles) |
| l3    | ✓    | ✓ (per-source lead-bias table)                  |
| l4    | ✓    | Phase 5+                                        |
| l6    | ✓    | Phase 6+                                        |
| chp/clp/wdp | ✓ | Phase 5+ (per-source specialist gates)     |

## Field coverage for NBM columns

Guided by NBM CO inventory audit (see [[nbm-cloud-fields-finding]]):

| Field | NBM available | Columns present  |
|-------|---------------|------------------|
| t     | ✓             | l1_nbm..l6_nbm   |
| dp    | ✓             | l1_nbm..l6_nbm   |
| ws    | ✓             | l1_nbm..l6_nbm   |
| wd    | ✓             | l1_nbm..l6_nbm   |
| wg    | ✓             | l1_nbm..l6_nbm   |
| sr    | ✓             | l1_nbm..l6_nbm   |
| cc    | ✓             | l1_nbm..l6_nbm   |
| ch    | ✓             | l1_nbm..l6_nbm   |
| cl    | ✗             | none (HRRR-only) |
| cm    | ✗             | none (HRRR-only) |
| h     | ✗             | none             |
| pr    | ✗             | none (POP-only)  |
| pa    | TBD           | none until confirmed |
| pp    | separate      | none (POP diff)  |

For fields with no NBM: `pick_source` is stamped `"hrrr"` unconditionally
by the selector; no `_nbm` columns emitted.

## Migration

Forward-only. Existing pair-log rows keep their shape (no `_nbm` columns,
no `pick_source`). New rows from the deploy point on carry both. The
selector fit script and any Phase 5+ consumer must tolerate absent
`_nbm` columns on pre-deploy rows (treat as `null`, exclude from NBM MAE
aggregates).

30-day retention window ages legacy rows out naturally. No rewrite job.

## Write path (Phase 1 wiring)

`forecast_snapshot.py` per tick:
- Stamps existing `{field}_lN` from the HRRR-side pipeline (unchanged).
- Reads `nbm_point_extract.json` from GCS (written by nbm-ingester CF).
- For each (field, lead) NBM emits: stamp `{field}_raw_nbm`, and later
  as NBM's L2..L6 come online, stamp `{field}_lN_nbm`.
- Stamps `{field}_pick_source` from the current
  `l1_selector_table.json`.

`forecast_error_log.py` joiner:
- Iterates each layer in `(l1, l2, l3, l4, l5, l6, chp, clp, wdp, l1r, nws)`
  as it does today for the HRRR side.
- Adds a second iteration over `(l1_nbm, l2_nbm, l3_nbm, l4_nbm, l6_nbm)`.
- Reads `{field}_lN_nbm` from the snapshot, emits `forecast_lN_nbm`
  and `error_lN_nbm` if present.
- Reads `{field}_pick_source`, emits `pick_source` if present.

Top-level `forecast` / `error` / `applied_layer` continue to be stamped
from the user-facing value (the picked source's applied output).

## Read paths that need Phase 5+ awareness

- `analysis/mae_over_time.py` — per-layer MAE aggregation; add
  per-source rollup.
- `analysis/l1_selector_fit.py` — nightly fit, computes MAE per
  (field, lead-band, source) and picks argmin.
- Debug page selector tile — reads `pick_source` per-hour.

Consumers reading only `forecast` / `error` / `applied_layer` are
unchanged.

## Scoreboard: dual-baseline lift (Joe request, 2026-08-18 PM)

The current scoreboard compares Production MAE against a single L1
baseline. With parallel cascades this hides the question that actually
matters. Post-Phase-1 (once `raw_nbm` is stamped), the scoreboard should
surface three deltas per (field, lead-band):

1. **Prod vs raw HRRR** — legacy metric; how much the stack beats raw HRRR.
2. **Prod vs raw NBM** — how much the stack beats raw NBM alone.
3. **Prod vs best raw** — Prod MAE minus `min(raw_hrrr, raw_nbm)` per pair,
   then aggregated. Answers "does the stack add value over just picking
   the better raw source per cell?" This is the sharp ship-decision
   metric for the selector's L3+ contribution.

The third number is the one that drives Phase-4+ ship decisions. Adding
correction layers that fail to beat "best raw" means we're paying
compute for negative lift.

UI shape (TBD, but locked as design intent): scoreboard gains a
"baseline" toggle (raw HRRR / raw NBM / best raw). Each cell's value +
color-coding computed against the selected baseline. Default view =
"best raw" once Phase 1 ships.

## Related

- [[nbm-cloud-fields-finding]] — why cl/cm/pr/h have no NBM columns.
- [[08-18-evening-handoff-build]] — parent design.
- [[option-1-full-parallel-plan]] — architecture.
