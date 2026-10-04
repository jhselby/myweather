---
name: 08-18-evening-handoff-build
description: "2026-08-18 evening handoff — fresh session opens as a BUILD session for option 1 (full parallel HRRR/NBM cascades, selector on finished L6 output). Self-contained: read this, start Phase 0. Supersedes the earlier 08-18 morning handoff which was for a design discussion."
metadata: 
  node_type: memory
  type: project
  originSessionId: 05215a48-aa86-4fcd-a0a7-ede577ff6ff7
  modified: 2026-08-18T21:41:40.426Z
---

# 08-18 evening handoff — BUILD session for option 1

**This file is self-contained.** A fresh session can read this alone and start
Phase 0. No need to reconstruct the design discussion; it's summarized below.

## Framing

This is a **build session**, not a discussion. Joe made the architectural
decision on 08-18 PM after a long design conversation. He wants option 1
(full parallel HRRR/NBM cascades, selector on finished L6 output). He said
"I want to do it right." He agreed to all recommendations in the plan.

Next time Joe opens the session, start Phase 0. Don't re-derive the design.
Don't re-open closed questions. Don't propose alternate architectures.

---

## What was decided

### The problem

The v0.6.431 pair-log stamping of NWS-gridpoint (NBM-derived) values enabled
a 14-day head-to-head against production. NBM beats Prod at leads ≥6h for
wg (+16%), wd (+11%), sr (+20%), and comparably for t/ws at long lead. HRRR
wins at short lead for a few fields. This forced a rethink of what "L1"
means in the cascade.

### v0.6.432 (uncommitted, DO NOT DEPLOY without discussion)

Shipped 08-18 evening as an "L1 router" but is actually a **post-cascade
override**. Cascade runs against Open-Meteo; at the end, for t/ws/wd at
leads ≥6h, cascade output is discarded and replaced with NWS values. Pair
log's `l1` slot still holds Open-Meteo. Two definitions of "L1" coexist,
debug page is incoherent. Only 3 fields, only ≥6h. Wrong architecture.

Currently **uncommitted in Joe's working tree**, NOT deployed to production.
Rip-out happens after Phase 4 selector clears its ship gate.

### The design discussion (08-18 PM)

Joe's mental model, articulated: the real question isn't "which raw is
closer to truth" but "which fully-corrected production output is closer to
truth per (field, lead-band)." That's a **selection** problem, not a
**correction** problem. The correction stack (L2-L6) we've been building
for months solves the wrong problem for source selection.

Four architectural options were considered:

1. **Full parallel L1-L6** — two complete pipelines, each fit against its
   own residuals, selector on finished L6 output.
2. **Parallel L1-L2, shared L3-L6** — captures short-lead divergence,
   shares long-lead corrections. Rejected: shared L3 corrupts corrections
   over a mixture distribution when selector coverage is uneven.
3. **L1-seed router** (what v0.6.432 shipped) — cheap, dishonest, cascade
   fights wrong residual model at routed cells. Rejected: baked-in MAE
   cost, invisible to debug.
4. **NBM only** — throw away HRRR wins. Rejected: violates Joe's
   secret-sauce thesis ("better than any single source because we pick
   per cell").

**Joe picked option 1.** Reason: it's the only version that never corrupts
corrections. The forever tax on doubled L4/L6 investigations (~10-30h over
6 months) is real but bounded; option 2's correction corruption is
unbounded. Doing it right beats doing it cheap.

### The digest question

Digest is a correction-shape tool that assumes a fixed cascade. Option 1
changes what "cascade" means mid-flight. Resolved:

- **Phases 0-4**: digest keeps running, ships HRRR-side only. Every ship
  stamped `backport_pending=nbm` in changelog + curated JSON.
- **Phase 5+**: digest switches to dual-source. New hypotheses fit against
  both sources, ship each side that clears its own gate.
- **Backport queue**: HRRR-side ships during the build get worked through
  NBM at Phase 5+ pace, no rush.
- **Selector-invalidated ships**: accepted cost. Not predicted, not avoided.

---

## Architecture (locked)

- Two parallel pipelines. Every layer parameterized by source.
  - HRRR: `L1_hrrr → L2_hrrr → L3_hrrr → L4_hrrr → L6_hrrr`
  - NBM:  `L1_nbm  → L2_nbm  → L3_nbm  → L4_nbm  → L6_nbm`
- Selector fires on **finished L6 output** — argmin recent MAE per
  (field, lead-band).
  - Lead bands: `{0-2h, 3-5h, 6-11h, 12-23h, 24-47h}`
  - Refit nightly from pair log.
  - Table in GCS: `l1_selector_table.json`.
- Pair log stamps **both** pipelines every tick — even cells the selector
  didn't pick. Selector needs both MAE streams to argmin honestly.
- User-facing forecast = selector's picked pipeline's L6 output.
- Rollback: disable NBM pipeline → selector falls through to HRRR
  everywhere → equivalent to today's behavior.

---

## Cross-phase rules (do not violate)

- **Every phase ends with a debug-page update.** Joe eyeballs the new layer
  before the next phase starts. Ship gate for each phase = layer wired +
  debug page shows it correctly + Joe explicit OK.
- **Do not start Phase N+1 until Phase N is verified working end-to-end
  and Joe has signed off on the debug page.**
- **Digest during Phases 0-4**: ships HRRR-side only, stamp
  `backport_pending=nbm`.
- **Digest at Phase 5+**: dual-source mode.
- **Selector table refit**: nightly cron.

---

## Phases

### Phase 0 — Foundation (~5-7h)

1. **NBM ingester Cloud Function** (new CF, separate from publisher)
   - Runs hourly. Fetches latest NBM CO grib for leads 1-47 from
     `s3://noaa-nbm-grib2-pds/blend.YYYYMMDD/HH/core/blend.tHHz.core.fFFF.co.grib2`
   - Extracts point values at Wyman Cove (42.5014, -70.875) for all fields
     NBM emits: t, dp, ws, wd, wg, sr, cc, cl, cm, ch, pa.
   - Writes `nbm_point_extract.json` to GCS `myweather-data`.
   - Memory tier: 1 GB (cfgrib is memory-hungry).
   - Source: adapt `scratchpad/nbm_extract_wide.py` (~120 lines, validated).
2. **120-day NBM backfill** — kick off first, runs overnight while
   everything else is built.
   - Extend `scratchpad/nbm_backfill_wide.py` to full 120 days.
   - Output: `scratchpad/nbm_cache_120d.jsonl`.
   - Verify: halves-stability check, no gaps.
3. **Pair-log schema extension**
   - Add per field: `raw_nbm`, `l1_nbm`, `l2_nbm`, `l3_nbm`, `l4_nbm`,
     `l6_nbm`, plus `pick_source` per (field, hour).
   - HRRR columns unchanged.
   - Migration: forward-only. Existing rows get `null` for NBM columns;
     new rows stamped both.
4. **Debug page update**: new tile on `corrections_debug.html` showing NBM
   ingester status (last successful run, extract age, GCS write timestamp),
   backfill coverage bar (120-day expected vs actual), pair-log schema
   version bumped indicator.
5. **Ship gate**: ingester writing GCS every hour, backfill complete and
   verified, pair-log schema extended, Joe OK's debug page.

### Phase 1 — NBM raw stamped in pair log (~3h)

1. Extend `forecast_snapshot.py`: on every tick, load NBM extract from GCS,
   stamp `raw_nbm` for every field NBM emits.
2. Fields NBM doesn't emit (h, pr): `raw_nbm = null`. Selector will treat
   as "single-candidate, always pick HRRR."
3. **Debug page update**: raw curves section gains NBM alongside HRRR per
   field. Side-by-side, same axes. Fields NBM doesn't emit show "no NBM
   data" tag.
4. **Ship gate**: `raw_nbm` populated within one CF tick of NBM ingester
   writing, debug page shows sane NBM values, Joe OK's.

### Phase 2 — NBM L2 (~5-7h)

1. New `weather_collector/processors/l2_nbm.py`: NBM-seed station-blend
   Kalman.
   - **Separate Kalman state per station per source.** HRRR-station-bias
     and NBM-station-bias are different objects. Never share.
   - Cold start: NBM Kalman initializes from scratch. Weeks to settle.
     During settle, `l2_nbm` MAE will be worse than `l2_hrrr`; selector
     will pick HRRR at those cells. Self-correcting.
2. Wire into collector: stamp `l2_nbm` in pair log per tick.
3. **Debug page update**: L2 section gains NBM curves + NBM Kalman state
   per station (bias, gain, settle-progress bar). Selector tile
   placeholder appears but reads "not yet armed."
4. **Ship gate**: L2_nbm behaving like a Kalman filter (bias tracks obs,
   gain decays with settle), Joe OK's.

### Phase 3 — NBM L3 (~4-5h)

1. New `analysis/l3_nbm_fit.py`: fits per-lead bias table against
   `l2_nbm` residuals from the 120-day backfill.
2. New `weather_collector/processors/l3_nbm.py`: applies table at
   forecast time. Stamps `l3_nbm` in pair log.
3. Curated JSON: `weather_collector/data/l3_nbm_curated.json` alongside
   existing (rename existing L3 curated files with `_hrrr` suffix for
   symmetry).
4. **Debug page update**: L3 section gains NBM lead-bias table alongside
   HRRR's. Per-lead residual curves side-by-side. `l3_nbm_curated.json`
   linked from the applicability map row.
5. **Ship gate**: NBM L3 fits look reasonable (per-lead bias shape
   sensible, no crazy coefficients), Joe OK's.

### Phase 4 — Selector on L3 output (~5-7h) — FIRST USER-FACING SHIP

1. New `weather_collector/processors/l1_selector.py`:
   - Loads `l1_selector_table.json` from GCS.
   - Per hour, per field: computes lead_h, looks up (field, lead-band) →
     source name. Sets user-facing forecast = `l3_<source>` output.
   - Stamps `pick_source[field][i]` per hour.
2. New `analysis/l1_selector_fit.py`:
   - Reads pair log, per (field, lead-band) computes MAE of `l3_hrrr`
     and `l3_nbm` over last 14 days, argmin, writes
     `weather_collector/data/l1_selector_table.json`.
   - Nightly cron.
3. **Debug page update**: selector state tile goes live — per-hour
   `pick_source` for every field, color-coded, hover shows recent-MAE
   margin that drove the pick. Selector table linked. SHIP_EVENTS
   annotation for v0.6.434. Applicability map L1 row rewritten for
   "picked per cell per band from selector table."
4. **Ship gate for Phase 4**: selector on L3 output delivers ≥90% of
   v0.6.432's measured long-lead lift on t/ws/wd. Otherwise investigate
   before proceeding to v0.6.432 ripout.

### v0.6.432 ripout (~2-3h) — after Phase 4 ship gate clears

Rip in one commit:

- `weather_collector/processors/l1_router.py` — delete.
- `weather_collector/collector.py` — remove call site (pre-`append_forecast_snapshot`).
- `forecast_snapshot.py` — remove `l1r` layer slot from t/ws/wd, remove
  from `_derive_applied_layer` walk order.
- `forecast_error_log.py` — remove `l1r` from per-layer emit loops.
- `decay_fit.py` — remove `l1r` from `per_layer_mae_by_lead`.
- `analysis/mae_over_time.py` — remove `l1r` from `PERMISSIVE_LAYER_KEYS`.
- `corrections_debug.html` — remove `l1r` from `LAYER_STYLE`,
  `FIELD_LAYERS`, SHIP_EVENTS 08-18 annotation. Remove
  `<field>_pre_router` reader.
- `js/obschart.js` — revert `maeAt()` to `l4` only (drop `l1r` preference).

Pair-log rows already stamped with `applied_layer="l1r"`: leave alone,
age out of 30-day window naturally.

### Phase 5 — NBM L4 (async, weeks)

- Wait for ~90 days of forward pair-log data with `l3_nbm` stamped.
- Fit regime library against NBM L3 residuals: frontal_t_bias,
  chp cell gate, wet-regime, sea-breeze, cove.
- Ship each per-regime table as its own gate walk clears.
- Selector migration: once `l4_nbm` is live for a field, selector re-fits
  against `l4_<source>` output for that field.
- Digest enters dual-source mode.

### Phase 6 — NBM L6 (async, months)

- Long-lead microclimate + Fix B rolling gate against NBM residuals.
- Same shape as Phase 5, longer wait.
- Selector fully migrated to L6 output when NBM L6 is live for all fields.

---

## Time estimate

Focused developer time to ship Phase 4 (user-facing selector on L3):
**~25-35h** across Phases 0-4 (debug-page updates included).

Plus v0.6.432 ripout: **~2-3h** once Phase 4 clears its ship gate.

Async wall time before Phase 5/6 can fit: weeks-to-months for forward data
accumulation.

---

## Resolved questions

Joe agreed to all recommendations 08-18 PM:

1. v0.6.432 rollback timing — leave running through Phase 4 build, rip
   once selector meets ship-gate. ✓
2. NBM ingester — new Cloud Function, clean isolation. ✓
3. Selector refit cadence — nightly cron. ✓
4. Legacy `l1r` pair-log rows — age out naturally over 30-day window. ✓
5. HRRR-direct as second HRRR source — deferred to phase 7+.
6. Cascade over-correction — moot in option 1 (per-source fits).
7. Digest during build — HRRR-side only ships, stamp `backport_pending=nbm`.
8. Debug page update per phase — required, in-scope for each phase.

---

## What already exists in scratchpad (reuse, don't rebuild)

- `scratchpad/nbm_extract_wide.py` — NBM point extractor, validated on
  3 days of data. Base for the CF.
- `scratchpad/nbm_backfill_wide.py` — parallel S3 backfill for wide
  (12-field) NBM extraction. Base for 120-day backfill.
- `scratchpad/nbm_backfill_narrow14.py` — narrow (4-field, 12-day) backfill.
- `scratchpad/nbm_cache_wide.jsonl` — 3 days × 12 fields NBM extracts.
- `scratchpad/nbm_cache_narrow14.jsonl` — 12 days × ws/wd/wg/sr extracts.
- `scratchpad/hrrr_extract.py` — HRRR-direct point extractor (phase 7+).
- `scratchpad/hrrr_cache.jsonl` — 14 days × 6 fields HRRR-direct.
- `scratchpad/run_benchmark_3way.py` + `router_scoreboard.py` — selector
  fit script skeleton, ~80% done.
- Pair log has `forecast_nws` stamped live since v0.6.431 (2026-08-18 AM)
  — accumulating forward data for NBM.

## Data + gotchas from the 08-18 discovery work

- Pair log `run_time` is **America/New_York local**, not UTC. Convert
  before joining NBM (UTC). Earlier 4h offset made `t` look catastrophic
  before correction.
- `pp` in pair log is Probability of Precipitation (0-100), not amount.
  NBM APCP mm/hr not comparable — needs separate POP extract.
- Nearest NBM 2.5km cell to Wyman Cove: 42.5136N, −70.884W (1.6km NW).
  Verify not inland at Beverly city center for cloud numbers.
- NBM `GUST:10m` is instantaneous; Tempest `gust_mph` obs is rolling max.
  Verify timebase alignment for wg before shipping.
- HRRR wind is derived from UGRD/VGRD at 10m instant; NBM's WIND:10m is
  blend's central estimate. Not identical semantics.
- cl/cm assigned from NBM message ORDER (1st `TCDC:reserved`=low,
  2nd=mid). If NBM convention reversed, labels swap. Both KILL, so
  verdict unchanged, but flag before wiring for real.

## 14-day scoreboard (from `router_scoreboard.py`)

```
field    L1     L3     L6     L12    L18    L24
t        Prod   HRRR   NBM    NBM    NBM    NBM
dp       Prod   Prod   NBM    NBM    NBM    NBM
ws       Prod   NBM    NBM    NBM    NBM    NBM
wd       Prod   Prod   NBM    NBM    NBM    NBM
wg       Prod   NBM    NBM    NBM    NBM    NBM
sr       HRRR   NBM    NBM    NBM    HRRR   NBM
```

These are Prod-vs-single-source raw comparisons. Selector will do better
than any row of this table because it picks per cell.

---

## First moves when session opens

1. `git status` — confirm v0.6.432 changes still uncommitted, working tree
   as expected.
2. Kick off 120-day NBM backfill in background (overnight S3 pull) so it
   runs while Phase 0 is being built.
3. Draft NBM ingester CF (new function, separate from publisher).
4. Design pair-log schema extension.
5. Build Phase 0 debug page tile.
6. Verify Phase 0 end-to-end, show Joe the debug page for sign-off.

**Do not** start Phase 1 until Phase 0 is verified and Joe signs off.
**Do not** touch v0.6.432 (leave it uncommitted, in place, unshipped).
**Do not** deploy anything without Joe explicit approval.
**Do not** run `make deploy-collector`, `git push`, or any command that
touches production without Joe explicit approval per session.

---

## Rules Joe cares about (do not violate)

- No `git push --force-with-lease`. Ever. See `CLAUDE.md`.
- Verify before guessing. `grep`, `cat`, `git status` first.
- One command at a time when output is needed.
- macOS sed: `sed -i ''`.
- Give Joe python scripts for edits, not generated files.
- Version-bump in `index.html` before commits. Claude does it.
- Changelog entries at TOP of `docs/CHANGELOG.md`, `Month Day, Year`
  format, `-` bullets.
- Test on localhost before pushing frontend changes.
- Don't invent problems. Don't add scope. Don't flip-flop under pressure.

---

## Reference links (memory)

- [[option-1-full-parallel-plan]] — the plan doc, same content organized differently.
- [[nbm-hrrr-l1-triage]] — 14-day scoreboard + data prep gotchas.
- [[08-18-handoff-discussion]] — earlier discussion handoff (historical).
- [[l1-router-rebuild-plan]] — SUPERSEDED, kept for reference.
