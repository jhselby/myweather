---
name: 08-19-morning-handoff
description: "2026-08-19 morning handoff. Option-1 build session (started 08-18 PM) shipped Phase 0/1 (v0.6.433) and Phase 2 (v0.6.434). Live in prod: parallel HRRR/NBM cascade stamping 9 raw_nbm + 5 l2_nbm fields per snapshot hour + pair-log row. NBM backfill at 26% coverage (663/2568 blobs); needs 3 more rounds to complete. Next: finish backfill, then Phase 3 (fit l3_nbm bias table from backfill residuals). This is the new READ-FIRST entry point; supersedes 08-18 evening handoff."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0f119ecf-9735-4bab-add3-866c32f13465
  modified: 2026-08-19T08:47:44.335Z
---

# 08-19 morning handoff — option-1 Phase 2 shipped, Phase 3 next

**Read this alone to pick up where 08-18 PM left off.** Prior handoff at
[[08-18-evening-handoff-build]] is now historical (Phase 0/1/2 completed
from it).

## What shipped 08-18 PM through 08-19 early AM

### v0.6.433 (Phase 0 + Phase 1) — NBM parallel-cascade foundation

- **NBM extractor** (`weather_collector/fetchers/nbm_point.py`): byte-range
  cfgrib parser of NBM CO 2.5km grib from public S3. Extracts 9 fields
  at Wyman Cove: t / dp / ws / wd / wg / sr / cc / ch / h.
- **NBM backfill CF** (`nbm_backfill/`): one-shot, `make deploy-nbm-backfill`.
  HTTP-triggered, writes `nbm_backfill/YYYYMMDD_HH.json` per cycle. 8 vCPU,
  8GB, 3600s timeout, cycle-level ThreadPool, resume-friendly.
- **NBM ingester CF** (`nbm_ingester/`): hourly, `make deploy-nbm-ingester`.
  Cloud Scheduler `myweather-nbm-ingest-schedule` fires :45 UTC. Writes
  `nbm_point_extract.json` for the collector to consume.
- **Phase 1 wiring**: collector loads the extract; `forecast_snapshot.py`
  stamps `{field}_raw_nbm` per hour (9 fields); `forecast_error_log.py`
  joiner emits `forecast_raw_nbm` + `error_raw_nbm` in pair-log rows.
- **Bundles v0.6.432 L1 router** (uncommitted before) — committed here as
  part of getting prod↔git back in sync after the collector deploy that
  shipped it. Rip-out plan preserved for after Phase 4.

### v0.6.434 (Phase 2) — L2_nbm plumbing

- **L2_nbm delta approach**: `l2_nbm = raw_nbm + (l2_hrrr − raw_hrrr)`.
  Station-derived corrections treated as model-agnostic in v1; refinable
  at Phase 5+ with station-vs-NBM bias.
- **Fields covered** = intersection(L2, NBM) minus derived (dp, cc) =
  **t / ws / wd / wg / h** (5 fields). wd uses signed circular delta.
- **`_NBM_FIELDS` in forecast_snapshot.py**: 9 (added h — the initial
  Phase 1 extractor missed RH:2m; caught on the 08-18 PM re-audit).
- **Fitter** (`decay_fit.py` + `analysis/mae_over_time.py`): per-layer
  aggregation loops + `PERMISSIVE_LAYER_KEYS` include `raw_nbm` +
  `l2_nbm`. Chart lines light up once a day of data accumulates.
- **Debug page** (`corrections_debug.html`):
  - LAYER_STYLE gets dashed `raw_nbm` + `l2_nbm` (parallel-cascade
    shadow rendering convention).
  - FIELD_LAYERS gets `raw_nbm` on all 9 NBM-emitted fields and
    `l2_nbm` on the 5 L2_nbm-covered ones.
  - 🎯 L1 selector placeholder tile added below the router tile —
    reads "not yet armed (Phase 4)".

### Cloud-fields finding (locked)

NBM CO product publishes 9 fields (see extractor). Does **NOT** publish:
- `cl`, `cm` — the 3× `TCDC:reserved` messages carry NCEP local level
  codes 195/196/197 with no defined meaning. Ignore them.
- `pr` — 55 unique field:level combos in the CO grib, zero pressure of
  any kind. NBM's product is impact-weather-focused; pressure users go
  to raw HRRR/GFS.
- `pa`, `pp` — deferred pending unit audit (APCP + POP).

Selector picks HRRR for cl / cm / pr / pa / pp / h forever (single-
candidate). Wait — h IS emitted; only cl/cm/pr are single-candidate
across the whole cloud-water column, plus pa/pp until audit.

Actually the correct list of forever-HRRR-only fields is: **cl, cm, pr**
(and pa/pp until the extract expands). Everything else is dual-source.

Reference: [[nbm-cloud-fields-finding]], [[pair-log-dual-source-schema]].

---

## Current state (verified 2026-08-19 04:45 EDT)

**Deployed and running:**
- `myweather-collector-<rev>` — stamping raw_nbm + l2_nbm per tick
- `myweather-nbm-ingest` — hourly :45 UTC via Cloud Scheduler, latest
  extract at 07:46 UTC (verified).
- `myweather-nbm-backfill` — no active invocations; idle
- All 3 CFs on the fixed extractor (9 fields including h).

**GCS:**
- `nbm_point_extract.json` fresh (updates hourly)
- `nbm_backfill/*.json` — **663 blobs / 2568 target = 26% coverage**
  - 30 distinct dates in the range 2026-05-01 to 2026-08-17
  - Coverage is 3-5 contiguous days per slice, big gaps between clusters
  - All blobs on 9-field schema (h present, no cl/cm garbage) — verified
    on both newest (2026-08-17) and oldest (2026-05-03) samples

**Pair log:** rows written from 08-18 evening deploy onward carry
`forecast_raw_nbm` + `error_raw_nbm` + `forecast_l2_nbm` + `error_l2_nbm`
(for fields NBM covers). ~10 hours of data now; enough to see the first
`raw_nbm` / `l2_nbm` lines appear in the debug-page chart.

**Debug page** (deployed):
- 🏗️ Phase 0 infra tile shows ingester status + placeholder for backfill
  coverage bar
- 🎯 Phase 4 selector placeholder tile
- Chart lines for raw_nbm + l2_nbm are wired in FIELD_LAYERS; will
  appear as data accumulates via mae_over_time publisher

**Git:** clean at v0.6.434 (`1594901`) pushed to origin/main. Working
tree has the usual curated-JSON drift + `.cache_*` files (unwanted per
CLAUDE.md rule).

**v0.6.432 router:** still LIVE in prod (not rolled back). Continues
overriding t/ws/wd at leads ≥6h. Rip-out remains scheduled for after
Phase 4 selector clears its ship gate.

---

## Immediate next moves (in order)

### 1. Finish NBM backfill (~3h wall time)

The 8 slice-with-15-days pattern only gets ~4 days per slice per 60min
call. Two options to complete:

**Option A (easy):** Refire all 8 slices with `overwrite=0` (default).
Each round skips already-done cycles, does ~4 more days per slice.
Need 3 more rounds to hit near-full coverage. Each round =
~60min wall time. Total ~3h.

**Option B (targeted):** Fire slices specifically at the gaps between
the 3-5-day clusters. Faster to full coverage. Gap ranges to target:
- 2026-08-03 through 2026-08-13 (11 days)
- 2026-07-19 through 2026-07-29 (11 days)
- 2026-07-04 through 2026-07-14 (11 days)
- 2026-06-19 through 2026-06-29 (11 days)
- 2026-06-04 through 2026-06-15 (12 days)
- 2026-05-20 through 2026-05-29 (10 days)
- 2026-05-05 through 2026-05-16 (12 days)

Fire ~7 15-day slices covering those + `overwrite=0`. Each ~60min. 8
slices in parallel = ~60min total wall time. Then check gaps + one more
pass.

Recommend **Option B** — more targeted, less wasted compute on already-
done cycles.

Fire pattern (from the Bash `run_in_background=true` curls, see the
08-18 evening session transcript for the exact curl template — same
URL, `--max-time 3700`, staggered ~45s apart to dodge cold-start rate
limits on max-instances=10).

### 2. Debug-page verification (5 min)

Once round 4 finishes: reload debug page, expand the L1 layer tiles
for t / ws / wd / wg / h. New `Raw (NBM)` line should appear on the
per-field accuracy chart (dashed light blue) alongside `Raw`. `L2 (NBM)`
line (dashed L2-blue) should appear on those 5 fields. Fifteen mins to
a day of data accumulation is enough for these lines to become visible
in the mae_over_time chart.

### 3. Phase 3 — fit l3_nbm bias table (~4-5h per handoff)

Per [[08-18-evening-handoff-build]] Phase 3:
- New `analysis/l3_nbm_fit.py`: fits per-lead bias table against
  `l2_nbm` residuals from the 120-day backfill (well, ~30 days of
  coverage now — reduced scope but same shape).
- New `weather_collector/processors/l3_nbm.py`: applies table at
  forecast time. Stamps `l3_nbm` in pair log.
- Curated JSON: `weather_collector/data/l3_nbm_curated.json`. Consider
  renaming existing L3 curated files with `_hrrr` suffix for symmetry
  (optional; not blocking).
- Debug page: L3 section gains NBM lead-bias table alongside HRRR's.
  Add `l3_nbm` to LAYER_STYLE + FIELD_LAYERS (same dash convention).
- Ship gate: NBM L3 fits look reasonable (per-lead bias shape sensible,
  no crazy coefficients), Joe OK.

Note: the pair-log now has `raw_nbm` + `l2_nbm` stamped, so the L3 fit
can compute residuals directly from pair-log rows (not just from
backfill blobs). Backfill is useful for extending the fit window
backward beyond the pair log's 30-day retention.

### 4. Phase 4 — selector (~5-7h) — first user-facing ship

Only starts after Phase 3 ship gate clears. Per handoff.

---

## Watch items / hygiene

- **Backfill CF cost:** 8 vCPU × 8GB × 60min × ~4 rounds ≈ 32 CPU-hours.
  Well within Cloud Functions Gen2 free tier + a few dollars.
- **Ingester CF cost:** 2 vCPU × 2GB × ~2min × 24/day ≈ 1 CPU-hour/day.
  Trivial.
- **Backfill CF max-instances=10:** don't fire more than 10 slices
  concurrently. Cold-start rate limit trips at 500 "no available
  instance" errors when >6-7 hit at once.
- **cfgrib bundled eccodes:** cfgrib's `ecmwflibs` wheel bundles the
  eccodes C library; no system package needed. If a CF deploy ever
  fails at import time with `libeccodes.so`-not-found, that changed.
- **Router (v0.6.432)** stays live until Phase 4 clears. Rip-out is a
  single-file revert of `weather_collector/processors/l1_router.py`
  (delete + remove call site in collector.py + remove `l1r` from
  applied_layer walk).

---

## Cross-cutting reminders (CLAUDE.md rules Joe cares about)

- No `git push --force-with-lease`. Regular `git push` works.
- Verify before guessing. `grep`, `cat`, `git status` first.
- One command at a time when output is needed.
- macOS sed: `sed -i ''`.
- Bump version in `index.html` first, then `python3 build.py` propagates
  to `version.json` + `sw.js`.
- CHANGELOG at TOP, `Month Day, Year` format, `-` bullets. Consolidate
  same-day entries.
- Test on localhost before pushing frontend changes (this session
  skipped for expediency since Joe was on mobile then desktop — future
  Joe: verify tiles look OK).
- Don't invent problems. Don't add scope. Don't flip-flop under pressure.

---

## Reference (memory)

- [[08-18-evening-handoff-build]] — original Phase 0-6 plan (Phase 0/1/2
  completed).
- [[option-1-full-parallel-plan]] — architecture doc, same plan.
- [[nbm-cloud-fields-finding]] — NBM extractor field mapping + audit.
- [[pair-log-dual-source-schema]] — pair-log schema + scoreboard-lift
  design intent.
- [[nbm-hrrr-l1-triage]] — 14-day scoreboard that seeded option-1.
