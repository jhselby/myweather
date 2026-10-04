---
name: nbm-cloud-fields-finding
description: 2026-08-18 Phase 0 build session — NBM CO grib inventory audit. NBM CO product publishes cc (TCDC:surface) and ch (TCDC:high cloud layer) only; there is NO LCDC/MCDC/low-cloud/mid-cloud entry in the 208-message inventory. Three TCDC:reserved messages at NCEP local level codes 195/196/197 exist but have no defined meaning per NCEP tables and MUST NOT be mapped to cl/cm/ch. Selector will always pick HRRR for cl/cm (single-candidate).
metadata: 
  node_type: memory
  type: project
  originSessionId: 0f119ecf-9735-4bab-add3-866c32f13465
  modified: 2026-08-19T01:12:13.205Z
---

# NBM cloud-field availability (Phase 0 finding, 2026-08-18)

## What NBM CO actually publishes for clouds

Grib inventory of `blend.tHHz.core.fFFF.co.grib2` (208 messages), audited
via full-index scan + eccodes typeOfFirstFixedSurface lookup:

| Grib message                    | typeOfFirstFixedSurface | App field |
|---------------------------------|--------------------------|-----------|
| TCDC:surface                    | 1 (ground/water surface) | cc        |
| TCDC:high cloud layer           | 234 (high cloud layer)   | ch        |
| TCDC:reserved (3 messages)      | 195, 196, 197            | **skip**  |
| CDCB:high cloud layer           | 234                      | (cloud base, unused) |
| CDCB:reserved (multiple)        | 195/196/197              | (unused)  |
| CDCTOP:reserved (multiple)      | 195/196/197              | (unused)  |
| CEIL:cloud ceiling              | —                        | (unused)  |
| RETOP:cloud top                 | —                        | (unused)  |

**No LCDC, no MCDC, no "TCDC:low cloud layer", no "TCDC:middle cloud layer".**

## Why the three TCDC:reserved messages must be ignored

NCEP GRIB2 local table 4.5 entries 195/196/197 are listed as "reserved for
local use" — no documented meaning. All three messages have identical
shortName="tcc", paramId=228164, discipline=0, category=6, number=1.
They cannot be reliably identified as low/middle cloud without out-of-band
documentation. Extractor v1 (2026-08-18 AM prior session) mistakenly
mapped them to cl/cm/ch — corrected same-day PM.

## Consequences for the option-1 selector

- **cc**: dual-source (HRRR + NBM). Selector chooses per (lead-band).
- **ch**: dual-source (HRRR + NBM). Selector chooses per (lead-band).
- **cl**: **single-candidate** — NBM emits nothing. Selector permanently
  picks HRRR. No L1_nbm entry for cl in the pair log.
- **cm**: same as cl — HRRR-only.

Downstream implication for Phase 5+ L4/L6 investigations:
- cc/ch NBM cascade needs its own residual library (regime tables, etc.)
- cl/cm NBM cascade is dormant — nothing to fit.

## Extractor mapping (locked in weather_collector/fetchers/nbm_point.py)

```
TMP:2 m above ground      → t   (K → °F)
DPT:2 m above ground      → dp  (K → °F)
WIND:10 m above ground    → ws  (m/s → mph)
WDIR:10 m above ground    → wd  (degrees)
GUST:10 m above ground    → wg  (m/s → mph)
DSWRF:surface             → sr  (W/m²)
TCDC:surface              → cc  (%)
TCDC:high cloud layer     → ch  (%)
RH:2 m above ground       → h   (%)
```

9 fields extracted. No cl/cm ever. No pr ever (NBM CO publishes no
PRES/PRMSL/MSLP anywhere in the 208-message inventory — HRRR-only).
pa/pp not extracted yet (needs separate audit for APCP unit + POP).

**Correction (2026-08-18 PM, same session as this note was written):**
An earlier draft of this file claimed NBM does not emit h. That was
wrong — RH:2m exists at idx line 96. Extractor + `_NBM_FIELDS` in
forecast_snapshot.py + memory index all updated.

## What to verify still

- pa: hunt for PRMSL / PRES:surface in a future audit. Add once confirmed.
- sr on older archive cycles: fetched-cycle log showed "no match for
  DSWRF:surface #0" on cycles pre-June 2026. NBM archive format may have
  changed; verify against backfill blobs from oldest dates once backfill
  completes.
- ws/wg NBM semantic vs Tempest obs timebase (handoff note flagged).

## Related

- [[08-18-evening-handoff-build]] — Phase 0 handoff (flagged cl/cm/ch
  ambiguity as verification item).
- [[option-1-full-parallel-plan]] — architecture doc.
