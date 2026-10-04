---
name: ch-chp-midlead-band-watch-08-10
description: 08-10 CLOSED same-day — chp bias traced to daytime valid hours in nw_flow + pre_frontal. Fixed via diurnal gate v0.6.401.
metadata: 
  node_type: memory
  type: project
  originSessionId: b8058893-d7b5-4544-a4d3-9f9dee94eef7
  modified: 2026-08-10T13:36:17.959Z
---

# RESOLUTION (08-10, same-day close)

Investigated instead of waiting. Pulled last 48h of ch pair-log rows grouped by regime × valid-hour-bucket × band. The +7.48 chp_bias at 12-23h was **not distributed** — concentrated in **daytime valid hours in nw_flow** (chp_bias +20.51, n=78) and **daytime valid hours in pre_frontal at 24-47h** (chp_bias +4.25, n=91). Nighttime cells in the same regimes: strong wins (-6 to -26% vs raw).

**Physical story**: chp persists cloud_high obs from run time into valid time. In post-frontal cold advection (nw_flow) or pre-frontal warm sector (pre_frontal), overnight residual clouds burn off by midday. Persistence carries the night obs into the daytime valid time → systematic over-forecast.

**Fix shipped v0.6.401** (`weather_collector/processors/ch_persistence_gate.py`):
- `_DIURNAL_SKIP_REGIMES = {nw_flow, pre_frontal}`
- `_DIURNAL_SKIP_HOURS = [10, 18)` America/New_York local
- New `_diurnal_skip()` check in `stamp_ch_persistence_gate` fire loop
- Diurnal skips exposed as `ch_persistence_gate.diurnal_skips_by_band` for monitoring

Field-aggregate ch remained a big win pre-fix (nighttime population dominated). Scoreboard cells for ch 12-23h and 24-47h expected to improve over the next 24-48h as the gate absorbs the daytime population.

If the diurnal gate causes NEW regression (over-restricts, e.g., daytime chp actually helped in unsampled nw_flow cells), watch signal is `diurnal_skips_by_band` count trend vs scoreboard cell recovery. Re-open only on evidence.

# ORIGINAL WATCH (superseded)

ch @ 12-23h and 24-47h are looking bad on the 08-10 24-hour scoreboard cell:

- **12-23h (n=240):** raw 6.77 → chp/prod_real 11.82. +74.6% vs raw. +102% vs pooled prod (5.86). Bias +7.48.
- **24-47h (n=447):** raw 11.51 → chp/prod_real 12.19. +5.9% vs raw. +65% vs pooled prod (7.38). Bias +5.72.
- **6-11h and 0-5h:** chp fine or helping.

Field-aggregate ch still winning: 7d prod_real 13.5 vs prod 16.7 (-19%). CV 27.8% (middle of the pack). This is a band-slice issue, not a field-level regression.

# Why chose to wait

- `h_chp_midlead_regression` this morning: STABLE, worst lead-20 at Δ+19.0% (chp behind l6, below +20% action floor). The 12-23h band = leads 12-23. Today's 24h band cut is the same drift the script tracks, now over the line in aggregate for that band.
- The watch script exists specifically to make this call. Acting on a single 24h cut would preempt the tool that's designed to trigger correctly.
- Same field just closed two watches CLEAN 08-09 ([[project_ch_chp_regression_watch_08_07]] + [[project_ch_persistence_gate_ship]]). Volatility is expected in chp; over-reacting risks whipsawing.

# Trigger for action

**08-11 (tomorrow):** re-check `h_chp_midlead_regression` verdict in the morning digest.

- If verdict trips ≥+20% at any mid-lead → escalate to option 3 (regime investigation). +7.5 bias at 12-23h suggests persistence anchoring to a high value that's not decaying to obs — likely regime-specific, so a targeted regime SKIP in `ch_persistence_gate_curated.json` is more likely to be the fix than a blanket band SKIP.
- If verdict still STABLE and 12-23h scoreboard cell still looks like today → escalate anyway (24h + 24h = 48h band-level damage on the debug page users see, without waiting further).
- If verdict STABLE and 12-23h cell has recovered → close this watch clean.

# How to apply

Read this on 08-11 morning triage. Cross-reference `h_chp_midlead_regression` verdict + today's `mae_over_time.json` last_24h_bands.ch.12-23 and 24-47 numbers. Update or close per the trigger rules above.

Related: [[project_ch_chp_regression_watch_08_07]], [[project_ch_persistence_gate_ship]], [[project_chp_midlead_regression_watch]], [[feedback_scorecard_lag_vs_accuracy_chart]].
