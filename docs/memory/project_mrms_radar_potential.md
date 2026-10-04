---
name: project-mrms-radar-potential
description: "MRMS (Multi-Radar Multi-Sensor) radar data as potential future data source for pp forecasting. Scoped 2026-08-06, NOT BUILT. Phased path: Phase 1 (radar as ground truth) 2-3 days, Phase 2 (radar current-state as pp input) ~1 week 20-40% Brier lift at 0-3h projected, Phase 3 (motion-vector nowcast) 2-3 weeks. Decision deferred pending pp workstream priority. Only relevant if pp remains a serious focus — currently pp is L1-only, ppbp Stage 1 queued but low-impact even if ships."
metadata: 
  node_type: memory
  type: project
  originSessionId: 57d4089d-4089-4ad5-a9a4-2ee10689764d
  modified: 2026-08-06T17:33:09.138Z
---

# MRMS radar data — potential avenue for pp forecasting

## Context

Scoped during 2026-08-06 discussion after `h_pp_frontal_platt_stage1` flipped HOLD, revealing that fixed-effect pp corrections have exhausted the pooled-bias calibration budget (Reliability = 0.012 = 1.2% of Brier). Question: what NEW data (not more correction) would open pp avenues?

Answer: radar is the single biggest lever for probabilistic-precip forecasting. We have NWP (HRRR/GFS/Pirate) but no radar. For 0-6h leads, radar extrapolation crushes any NWP. Adding it would change the INPUT signal, not just correct the current one.

## What MRMS is

NOAA Multi-Radar Multi-Sensor: fuses ~180 NEXRAD radars + satellite + rain gauges into national precipitation analysis. Updated every 2 min. Free. Publicly available.

Key products for pp use:
- **PrecipRate** — current instantaneous rain rate (mm/hr), 1km resolution, 2-min cadence.
- **RadarOnly_QPE_01H** — radar-derived precipitation total for last 1 hour.
- **MergedReflectivityQCComposite** — composite reflectivity (dBZ) — the classic "radar image."
- **PrecipFlag** — precipitation type classification (rain/snow/mixed).

## Data access

- **AWS Open Data**: `s3://noaa-mrms-pds/` — free public archive, no auth.
- **NCEP/NOMADS**: real-time GRIB2 files.
- **Format**: GRIB2 (meteorological standard). Python decode via `pygrib` or `xarray + cfgrib`. Command-line via `wgrib2`. `ecCodes` bindings can be finicky in Cloud Function environments.
- **Volume**: national files 5-50 MB; regional subset (Salem area ~100km box) ~100 KB per fetch.

## Phased implementation

### Phase 1 — Radar as ground truth (easiest, 2-3 days)

Don't forecast with it yet. Use it to **measure** how good existing pp is.

- Fetch MRMS PrecipRate for Salem area at each collector tick.
- Store as `radar_precip_rate_current` in weather_data.
- Compare to existing point obs (KBVY, WU): does radar say it rained when point stations say no? Radar is more spatially complete → catches rain that misses stations.
- Recompute Brier + climatology against radar-truth rather than point-obs-truth. Numbers likely change — current pp scoring may have false-negative-heavy ground truth.

### Phase 2 — Radar current-state as pp input (medium, ~1 week)

Use radar AS INPUT to pp, not just as scorer.

- Add `radar_precip_rate_current` and `radar_precip_last_1h` to what collector writes.
- For 0-3h pp: if radar shows active precip, boost near-term pp. If radar shows nothing and HRRR says pp=40%, damp near-term pp.
- Rules-based initially, learn thresholds from held-out data.
- Projected: 20-40% Brier lift at 0-3h leads based on published MRMS-blend literature.

### Phase 3 — Radar nowcast (hard, 2-3 weeks)

Full motion-vector nowcasting. Last 3-6 radar frames → extract precip motion field → project current echoes forward 30-90 min. Off-the-shelf libraries: `pysteps`, `Rainymotion`. Real weather-science territory. Blend nowcast with NWP-based pp.

Where meteorological services get their "next 60 min" precip guidance. Skill at 0-60 min crushes any NWP model.

## Realistic caveats

1. **Radar QPE has biases** — bright band, ground clutter, low-altitude beam blockage. Not gospel truth. Boston/Salem area well-covered by KBOX radar though.
2. **Nowcast decay**: 0-30 min radar extrapolation beats NWP. 30-90 min competitive. Past 90 min NWP wins.
3. **Cloud Function memory**: GRIB2 decoding is memory-heavy. May need collector memory bump.
4. **Real dependency chain**: ecCodes + GRIB2 libs + S3 client + subset tools. Not one-line pip install.

## Ranked with alternatives

For pp specifically, in order:
1. **MRMS radar** (this). Biggest lever.
2. **NWS QPF** — expert forecaster product. May already be in NWS gridpoint API being called.
3. **Ensemble (HREF/GEFS)** — proper probabilistic inputs, could retire calibration entirely.
4. **NOAA hourly climate normals** — real climatology, sharpens skill-score comparisons.

## Decision status

**Not scheduled. Deferred until pp workstream priority firms up.**

- If ppbp Stage 1 succeeds and pp becomes a serious focus → MRMS Phase 1 is the honest next step.
- If ppbp fails and pp is parked → no MRMS work, redirect effort to other fields.

## Related

- `[[project_pp_recalibration_session]]` — the workstream this would rescue.
- `[[project_ppbp_workstream]]` — the correction-side alternative currently in flight.
- `[[project_pp_brier_reliability]]` — measurement framework MRMS Phase 1 would sharpen.
