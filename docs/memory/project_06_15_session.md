---
name: project-06-15-session
description: "26-ship session 2026-06-15 — R5 already passing thresholds, L5 SHIP candidate at 31.6% MAE drop, three real bugs caught by 'analysis-script-first' discipline. Key handoff for the 06-19 and 06-22 decisions."
metadata: 
  node_type: memory
  type: project
  originSessionId: 43ac5ed4-a539-4e44-be37-7cbc5fe435f9
---

## Headline: two corrections teed up to ship next week + three real bugs caught

### Date-gated decisions waiting

**2026-06-19 (Friday) — R5 cove correction first read**
- Day-4 already passes both regime thresholds per `analysis/r5_cove_analysis.py`:
  - S-half sea-breeze warming: mean Δ = +1.73°F (threshold > +1°F), n=147, std=2.06°F
  - 06-10 EDT offshore cooling: mean Δ = −1.75°F (threshold < −1°F), n=50, std=1.48°F
- Decision Friday: re-run on full 7 days of data; if it still passes, flip `cove_correction.ENABLED = True` in `weather_collector/processors/cove_correction.py`.
- Code is ready. Lookup table already populated. Live stamps verified working via G1 debug-page card.

**2026-06-22 (Monday) — L5 solar regime correction + walk-forward re-run #2**
- L5 has a STRONG SHIP verdict from today's evaluation: **overall MAE drops 31.6%, 7/8 regimes improving by ≥3%**.
- Re-run `python3 analysis/l5_solar_analysis.py` on Monday. If verdict holds, flip `solar_correction.ENABLED = True`.
- Also: walk-forward re-run #2 vs today's `walkforward_15jun` verdict (drop cm, pp from L3, clear L4). If they agree, ship the new whitelist.
- Also: R4 first read (date shifted from 06-19 to 06-22 due to today's fetcher bug — see below).

### The L5 iteration arc — instructive for future correction design

Three passes, each one directly addressing the prior diagnosis:

1. **Initial sketch** (regime-only, biases from `state_stratified_accuracy.json`): HOLD at 0.7% MAE drop, 0/8 regimes improving. Diagnosis: state_stratified averages across nighttime zeros, masking the daytime signal.
2. **Daytime-only recompute** (`l5_recompute_biases.py`): HOLD at 4.9% MAE drop, 2/8 regimes. Just shy of the 5% threshold. Diagnosis: within-regime bias varies by hour of day, averaging across hours produces systematically wrong corrections for any specific hour.
3. **Regime × hour stratification** (`l5_recompute_biases_hourly.py`): **SHIP at 31.6% MAE drop, 7/8 regimes.** ne_flow regime swings from −238 W/m² at 10:00 to +247 W/m² at 14:00 — same regime, opposite biases. Hour-of-day was the missing dimension.

**Pattern to remember:** when a regime-conditional correction underperforms, the next refinement is usually adding another conditioning dimension (hour-of-day, season, sub-regime). Don't abandon a correction with directional signal; refine the index.

### Three real bugs caught — "analysis-script-first" discipline paid off

All three discovered by trying to USE the data in a downstream analysis, not by passively monitoring:

1. **R4 fetcher bug** (caught by `r4_spread_analysis.py`): `fetch_hourly_gfs_7day` was missing `models=gfs_seamless`, so Open-Meteo defaulted to "best available" (HRRR for 0-48h). For three days `gfs_l1_log.json` had been capturing HRRR data, not GFS — spread = 0 by construction. Fix: added `models: gfs_seamless`. R4 first-read date shifts from 06-19 → 06-22 (need 7 days of clean data).
2. **Pair-log 6× inflation** (caught yesterday during audit, manually fixed today): joiner emitted one pair per 10-min collector tick when only 1 per hour represents an independent atmospheric observation. Today's manual dedup: 4.6 GB → 819 MB instantly. MAE numbers shifted upward 20-30% across the board (expected behavior of honest stats vs inflated).
3. **L5 live stamp regime null** (caught while verifying G1 card after deploy): `derived.state.regime_synoptic` is populated only by the Joiner for pair-log records, not for the live forecast. Added an inline classifier call inside `stamp_solar_correction` so the G1 debug-page card actually has a regime to look up.

**Principle:** the best bug-finder is downstream USE of upstream data. Schedule analysis-script-first work *before* date-gated decisions so bugs surface in prep time, not at the deadline.

### What shipped today (26 versions: v0.6.78 through v0.6.102 + v0.6.103 changelog consolidation)

Major themes:
- Backtest framework Phase 2-4 (config-driven decay_apply + replay runner + multi-config sweep + debug page B1 section)
- R0 audit table overhaul (Yes/No, L2 column, bias subtext, missed-opportunity banner, color-coded Applied?)
- L3/L4 historical-fit APPLIED/diagnostic badges
- POP per-layer L4 tracking unified
- Frontal detector end-to-end validation
- Manual pair-log dedup
- R5 cove correction + R4/R5 first-read scripts + L5 solar regime correction (3 iteration passes)
- Shadow whitelist tuner
- New debug-page sections G1 (gated candidates) + S1 (shadow tuner)
- Multiple debug-page text sweeps

### State of all open hypotheses (post-today)

| Hypothesis | State | Next decision |
|---|---|---|
| R2 state-stratified | Active, drives L5 design | Continuous monitoring |
| R4 HRRR/GFS spread | Data collection (post-fetcher-fix) | 06-22 first read |
| R5 cove warming | Day-4 passes thresholds | 06-19 first read |
| L5 solar regime | 31.6% SHIP verdict on day-15 data | 06-22 confirmation re-run |
| L3 cm-and-pp drop | walkforward_15jun verdict | 06-22 walk-forward re-run #2 |
| Shadow whitelist tracking | Just started logging | 90 days of data for agreement analysis |
| Frontal detector | End-to-end validated, no real fronts seen yet | Wait for next front |

### Late-evening addition (technically 2026-06-16 UTC)

**v0.6.103: Wind direction consensus guardrail.** Joe spotted that the displayed wind was E (92°) while his flagpole (and KBVY METAR, KBOS, NOAA buoy, 12 of 14 Tempest stations) all said NW (~310°). Investigation: `select_observed_wind` picks the highest-gust waterfront Tempest for direction, no consensus check. Neptune Rd was reading 18.3 mph gust + 92° (sensor likely 180°-misaligned or transiently drifting), beating Willow Rd's correct 6.3 mph + 319°. Speed had octant-median smoothing + WU sanity cap; direction had neither.

Fix: added `_circular_mean` + `_circular_diff_deg` helpers to `wind_blend.py`. After the existing picker chooses, computes consensus across all reliable direction sources (KBVY + KBOS + buoy + valid Tempests, requires n≥3). If chosen is >90° off consensus, rejects and uses consensus instead. Stamps `current.wind_direction_guardrail = {rejected_value, rejected_source, consensus_value, consensus_n, offset_deg}` for debug visibility.

Handles transient AND chronic sensor failures the same way — no permanent station cull required. Generalizes to any future sensor drift.

### How to apply

When the user (Joe) returns:
- If it's 06-19: run `python3 analysis/r5_cove_analysis.py` to confirm. If SHIP, edit `cove_correction.ENABLED = True`, deploy.
- If it's 06-22: run all three of `l5_solar_analysis.py`, `r4_spread_analysis.py`, and the walk-forward validator. Decide on each.
- Otherwise: passive observation. Glance at audit table for unexpected changes. Don't actively iterate on L5 — the SHIP verdict is solid.

### Related

- [[project-r4-r5-hypotheses]] — original hypothesis design
- [[project-correction-stack]] — architecture reference
- [[project-06-08-to-06-22-plan]] — calendar plan this session executes on
- [[project-sunset-calibration]] — separate post-azimuth-fix calibration work
- [[project-gcs-soft-delete-trap]] — the 06-13 finding that recurs in the "audit upstream assumptions" pattern
