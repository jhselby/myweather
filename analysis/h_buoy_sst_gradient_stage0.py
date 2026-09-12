"""Stage 0 — Buoy 44013 SST land-sea gradient as a sea-breeze predictor.

Hypothesis: sea-breeze intensity is physically driven by the land-sea temperature
gradient. When |t_forecast − sst_buoy| is large, sea-breeze onset is earlier
and stronger; wd/ws/sr forecasts in sea-breeze-eligible regimes should differ
systematically from small-gradient days.

Feature: Δ = t_forecast(lead=0) − sst_44013 at run_time. Bin. Analyze MAE
of wd/ws/sr in the sea_breeze regime (and its neighbors: se_flow, calm)
as a function of Δ.

Ship shape (if it clears):
  (a) SST-gradient C1 axis on sea-breeze-eligible cells — confidence widens
      when Δ is large (uncertain onset timing).
  (b) OR conditional Lsb: extend live sea-breeze specialist with an SST-
      gradient modifier that shifts its trigger threshold.

Status: PLUMBING GAP. Buoy 44013 water temp is fetched every tick (see
weather_collector/fetchers/salem_water.py + collector.py:174 stores it as
weather_data['buoy_44013'] and salem_water_temp_f as fallback), but the
value is NOT included in the pair-log per row. No historical SST timeline
exists for the pair-log period, so this Stage 0 cannot yet run against
real data.

Plumbing to unblock:
  1. Add per-tick SST snapshot to a rolling log (analysis/sst_44013_log.jsonl
     or equivalent), keyed by run_time.
  2. Backfill from ~30d of GCS weather_data.json history if the field was
     already stored there.
  3. Join the log to the pair log by run_time in this Stage 0.

Once plumbed, the analysis body is:
  1. For each row with obs_time in {sea_breeze, se_flow, calm} regime,
     fetch sst_at_run_time from the SST log.
  2. Compute Δ = t_forecast_at_run_time − sst.
  3. Bin by Δ quartile. Compute wd/ws/sr MAE per bin.
  4. Verdict: PROMOTE if Q4/Q1 MAE ratio ≥ 1.30 halves-stable in ≥ 3
     (field, regime) cells with n ≥ 200 each.
"""

VERDICT = "STAGE 0 SCAFFOLDING — buoy 44013 SST gradient mechanism-test blocked on SST-log plumbing. Buoy value fetched but not written to per-run log or pair-log rows. See docstring for plumbing spec."
print(VERDICT)
