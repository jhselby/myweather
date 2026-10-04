---
name: option-1-full-parallel-plan
description: "2026-08-18 evening — Joe picked option 1 (full parallel HRRR/NBM cascades, selector on finished output). This is the scoped build plan for v0.6.434 and beyond. Supersedes the earlier project_l1_router_rebuild_plan.md."
metadata: 
  node_type: memory
  type: project
  originSessionId: 05215a48-aa86-4fcd-a0a7-ede577ff6ff7
  modified: 2026-08-18T21:39:15.428Z
---

# Option 1 — Full Parallel Cascade Build Plan

Joe's decision, 2026-08-18 evening: build two complete pipelines (HRRR and NBM),
each with its own L1→L6 stack fit against its own residuals, and select between
finished outputs per (field, lead-band). "I want to do it right."

Supersedes [[l1-router-rebuild-plan]]. That doc's L1-seed router is now the
wrong shape — it fights the cascade with mis-fit residuals.

---

## Architecture (locked)

- Two parallel pipelines. Every layer parameterized by source.
  - HRRR pipeline: `L1_hrrr → L2_hrrr → L3_hrrr → L4_hrrr → L6_hrrr`
  - NBM pipeline: `L1_nbm  → L2_nbm  → L3_nbm  → L4_nbm  → L6_nbm`
- Selector fires on **finished L6 output** — argmin recent MAE per (field, lead-band).
  - Bands: `{0-2h, 3-5h, 6-11h, 12-23h, 24-47h}`
  - Refit nightly from pair log.
  - Table lives in GCS: `l1_selector_table.json`.
- Pair log stamps **both** pipelines every tick — even cells the selector
  didn't pick. Selector needs both MAE streams to argmin honestly.
- User-facing forecast = selector's picked pipeline's L6 output.
- Rollback: disable NBM pipeline → selector falls through to HRRR everywhere.

## Why not option 2 (parallel L1-L3, shared L4-L6)

L4 and L6 fit against a mixture distribution when the selector's coverage is
uneven; corrections are systematically wrong in ways that get worse as
selector picks shift over time. Option 1 is the only version that never
corrupts corrections. The ~10-30h forever tax on doubled L4/L6 investigations
is real but bounded; option 2's correction corruption is unbounded.

## Why not option 3 (v0.6.432 L1-seed router) or option 4 (NBM only)

- Option 3: cascade fights wrong residual model on losing source. Baked-in
  MAE cost at every routed cell, invisible to debug page.
- Option 4: throws away HRRR's short-lead wins. Violates secret-sauce thesis
  (better than any single source because we pick per cell).

---

## Cross-phase rules

- **Every phase ends with a debug-page update.** Joe eyeballs the new layer
  before the next phase starts. Ship gate for each phase = layer wired +
  debug page shows it correctly + Joe explicit OK.
- **Digest during Phases 0-4**: keeps running, ships HRRR-side only, every
  ship stamped `backport_pending=nbm` for Phase 5+ to work through.
- **Digest at Phase 5+**: switches to dual-source. New hypotheses fit
  against both sources, ship each side that clears its own gate.
- **Selector-invalidated ships**: accepted cost. HRRR-side corrections
  shipped during the build that the selector later moots at picked cells
  are wasted work we don't try to predict.

## Ship phases

### Phase 0 — Foundation (~5-7h with debug)

- **NBM ingester Cloud Function**
  - New scheduled CF (recommend separate from publisher CF for clean isolation
    and independent redeploy — confirm with Joe).
  - Runs hourly. Fetches latest NBM CO grib for leads 1-47.
  - Extracts point values at Wyman Cove (42.5014, -70.875) for all fields NBM
    emits: t, dp, ws, wd, wg, sr, cc, cl, cm, ch, pa.
  - Writes `nbm_point_extract.json` to GCS `myweather-data` bucket.
  - Source: adapt `scratchpad/nbm_extract_wide.py` (~120 lines, validated).
  - Memory tier: 1 GB (cfgrib decode is memory-hungry).
- **120-day NBM backfill**
  - Run `scratchpad/nbm_backfill_wide.py` extended to full 120 days.
  - Overnight S3 pull, parallelized. Output to `scratchpad/nbm_cache_120d.jsonl`.
  - Verify integrity before use (halves-stability check, no gaps).
- **Pair log schema extension**
  - Add columns per field: `raw_nbm`, `l1_nbm`, `l2_nbm`, `l3_nbm`, `l4_nbm`,
    `l6_nbm`, plus `pick_source` per (field, hour).
  - HRRR columns unchanged.
  - Migration: forward-only. Existing rows get `null` for NBM columns; new
    rows stamped both.

- **Debug page update**: new tile on `corrections_debug.html` showing NBM
  ingester status (last successful run, extract age, GCS write timestamp),
  backfill coverage bar (120-day expected vs actual), pair-log schema
  version bumped indicator. Joe eyeballs before Phase 1.

### Phase 1 — NBM raw stamped in pair log (~3h with debug)

- `forecast_snapshot.py` extended: on every tick, load NBM extract from GCS,
  stamp `raw_nbm` for every field NBM emits.
- Fields NBM doesn't emit (h, pr): `raw_nbm = null`. Selector treats as
  "single-candidate, always pick HRRR."
- Verify: `raw_nbm` populated within one CF tick of NBM ingester writing.

- **Debug page update**: raw curves section gains NBM alongside HRRR per
  field. Side-by-side, same axes. Fields NBM doesn't emit show "no NBM
  data" tag. Joe eyeballs raw NBM values look sane before Phase 2.

### Phase 2 — NBM L2 (~5-7h with debug)

- New `l2_nbm.py`: NBM-seed station-blend Kalman. Separate Kalman state
  per station per source (HRRR-station-bias and NBM-station-bias are
  different objects — never share).
- Cold start: NBM Kalman initializes from scratch. Weeks to settle.
  During settle, `l2_nbm` MAE will be worse than `l2_hrrr`; selector
  will pick HRRR at those cells. Self-correcting.
- Stamp `l2_nbm` in pair log per tick.

- **Debug page update**: L2 section gains NBM curves + NBM Kalman state
  per station (bias, gain, settle-progress bar since it's cold-started).
  Selector tile placeholder appears but reads "not yet armed." Joe
  eyeballs L2 NBM behavior looks Kalman-shaped before Phase 3.

### Phase 3 — NBM L3 (~4-5h with debug)

- `l3_nbm_fit.py`: fits per-lead bias table against `l2_nbm` residuals from
  the 120-day backfill.
- `l3_nbm.py`: applies table at forecast time. Stamps `l3_nbm` in pair log.
- Curated JSON: `l3_nbm_curated.json` alongside existing `l3_hrrr_curated.json`
  (existing files renamed with `_hrrr` suffix for symmetry).

- **Debug page update**: L3 section gains NBM lead-bias table alongside
  HRRR's. Per-lead residual curves side-by-side. `l3_nbm_curated.json`
  linked from the applicability map row. Joe eyeballs NBM L3 fits look
  reasonable before Phase 4.

### Phase 4 — Selector on L3 output (~5-7h with debug)

- **First ship of user-facing selector.** Pipeline stops at L3 for both
  sources initially; L4/L6 still hrrr-only during bootstrap (see Phase 5-6).
- `l1_selector.py`:
  - Loads `l1_selector_table.json` from GCS.
  - Per hour, per field: computes lead_h, looks up (field, lead-band) →
    source name. Sets user-facing forecast = `l3_<source>` output.
  - Stamps `pick_source[field][i]` per hour.
- `l1_selector_fit.py`:
  - Reads pair log, per (field, lead-band) computes MAE of `l3_hrrr`
    and `l3_nbm` over last 14 days, argmin, writes
    `l1_selector_table.json`.
  - Nightly cron.
- **Ship gate for Phase 4**: selector on L3 delivers ≥90% of v0.6.432's
  measured long-lead lift on t/ws/wd. Otherwise investigate before
  ripping out v0.6.432.

- **Debug page update**: selector state tile goes live — per-hour
  `pick_source` for every field, color-coded, hover shows recent-MAE
  margin that drove the pick. Selector table (`l1_selector_table.json`)
  linked. SHIP_EVENTS annotation for v0.6.434. Applicability map L1 row
  rewritten for "picked per cell per band from selector table." Joe
  eyeballs full end-to-end before v0.6.432 ripout.

### Phase 5 — NBM L4 (async, weeks)

- Wait for ~90 days of forward pair-log data with `l3_nbm` stamped.
- Fit regime library against NBM L3 residuals: frontal_t_bias,
  chp cell gate, wet-regime, sea-breeze, cove.
- Ship each per-regime table as its own gate walk clears.
- Selector migration: once `l4_nbm` is live for a field, selector
  re-fits against `l4_<source>` output for that field.

### Phase 6 — NBM L6 (async, months)

- Long-lead microclimate + Fix B rolling gate against NBM residuals.
- Same shape as Phase 5, longer wait.
- Selector fully migrated to L6 output when NBM L6 is live for all fields.

### Concurrent — v0.6.432 ripout (~2-3h)

- **Timing**: rip out only after Phase 4 selector delivers ≥90% of v0.6.432's
  lift. See [[08-18-handoff-discussion]] question 1 — Joe's call, but the
  ship-gate makes it low-risk to leave running through the build.
- Rip:
  - `weather_collector/processors/l1_router.py` — delete.
  - `weather_collector/collector.py` — remove call site (was pre-`append_forecast_snapshot`).
  - `forecast_snapshot.py`: remove `l1r` layer slot from t/ws/wd,
    remove from `_derive_applied_layer` walk order.
  - `forecast_error_log.py`: remove `l1r` from per-layer emit loops.
  - `decay_fit.py`: remove `l1r` from `per_layer_mae_by_lead`.
  - `analysis/mae_over_time.py`: remove `l1r` from `PERMISSIVE_LAYER_KEYS`.
  - `corrections_debug.html`: remove `l1r` from `LAYER_STYLE`, `FIELD_LAYERS`,
    SHIP_EVENTS 08-18 annotation. Remove `<field>_pre_router` reader.
  - `js/obschart.js`: revert `maeAt()` to `l4` only (drop `l1r` preference).
- Pair-log rows already stamped with `applied_layer="l1r"`: leave alone,
  age out of 30-day window naturally. See [[08-18-handoff-discussion]]
  question 6.

---

## Time estimate

Focused developer time to ship Phase 4 (user-facing selector on L3):
**~25-35h** across Phases 0-4 (debug-page updates included) plus
v0.6.432 ripout (~2-3h).

Async wall time before Phase 5/6 can fit: weeks-to-months for forward data.

---

## Open questions — RESOLVED 2026-08-18 PM

Joe agreed to all recommendations:

1. **v0.6.432 rollback timing** — Leave running through Phase 4 build, rip
   once selector meets ship-gate. ✓
2. **NBM ingester** — New Cloud Function, clean isolation. ✓
3. **Selector refit cadence** — Nightly cron. ✓
4. **Legacy `l1r` pair-log rows** — Age out naturally over 30-day window. ✓
5. **HRRR-direct as second HRRR source** — Deferred to phase 7+.
6. **Cascade over-correction** — Moot in option 1 (per-source fits).

## Digest handling during the build — RESOLVED

- **Phases 0-4**: digest runs as today, ships HRRR-side only. Every ship
  stamped `backport_pending=nbm` in changelog + curated JSON.
- **Phase 5+**: digest switches to dual-source mode. New hypotheses fit
  against both sources, ship each side that clears its own gate.
- **Backport queue**: HRRR-side ships during the build get worked through
  NBM at Phase 5+ pace, no rush.
- **Selector-invalidated ships**: accepted cost of running two things
  at once. Not predicted, not avoided.

---

## Sequencing rules (do not violate)

- Phase 0 must complete before Phase 1 (need CF live to stamp raw).
- Phase 1 must complete before Phase 2 (need raw stamped to derive L2).
- Phase 2 must complete before Phase 3 (L3 fits against L2 residuals).
- Phase 3 must complete before Phase 4 (selector needs both L3 streams).
- Phase 4 must clear ship gate before v0.6.432 ripout.
- Phases 5-6 wait for forward data; do not attempt to fit on <90 days.

---

## What already exists (in scratchpad, ready to reuse)

- `scratchpad/nbm_extract_wide.py` — NBM point extractor, validated
- `scratchpad/nbm_backfill_wide.py` — parallel S3 backfill
- `scratchpad/nbm_cache_wide.jsonl` — 3 days × 12 fields
- `scratchpad/nbm_cache_narrow14.jsonl` — 12 days × 4 fields
- `scratchpad/hrrr_cache.jsonl` — 14 days × 6 fields (HRRR-direct, phase 7+)
- `scratchpad/run_benchmark_3way.py` — selector fit script skeleton, ~80% done
- Pair log has `forecast_nws` stamped live since v0.6.431 (2026-08-18 AM)

---

## First move when Joe returns

Open questions resolved. Kick off Phase 0:

1. Kick off 120-day NBM backfill in background (overnight S3 pull) — start
   this first, it runs while everything else is being built.
2. Draft NBM ingester CF (new function, separate from publisher).
3. Design pair-log schema extension (add columns per field for
   `raw_nbm`, `l1_nbm`, `l2_nbm`, `l3_nbm`, `l4_nbm`, `l6_nbm`,
   `pick_source`).
4. Build Phase 0 debug page tile (NBM ingester status + backfill coverage).
5. Verify Phase 0 end-to-end, Joe eyeballs debug page, OK to proceed.

Do not start Phase 1+ until Phase 0 is verified working end-to-end and Joe
signs off on the debug page.
