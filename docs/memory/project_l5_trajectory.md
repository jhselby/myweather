---
name: project-l5-trajectory
description: "L5 (solar regime correction) trending clear as of 2026-06-27: 6 SHIP days / 0 HOLD over trailing 7-day window, 12-cycle SHIP streak. One more clean SHIP day flips solar_correction.ENABLED = True. Earliest plausible promotion 2026-06-28."
metadata: 
  node_type: memory
  type: project
  originSessionId: d1501df5-ccca-43fa-9f71-7dafb1d5eebe
---

## State at 2026-06-27 (current)

Live read from `l5_gate_history.json` via the divergence report: **6 SHIP days / 0 HOLD / 12-cycle SHIP streak** over the trailing 7-day window. One more clean SHIP day clears the gate.

Trajectory progression:
- 06-21: 1/7 SHIP (pre-refit) → 3/7 SHIP (post-refit)
- 06-24: 4/7 SHIP, 6-cycle streak
- 06-25: 4/7 SHIP, 6-cycle streak
- 06-26: 5/7 SHIP, 8-cycle streak
- 06-27: **6/7 SHIP**, 12-cycle streak

Earliest promotion is now **2026-06-28** if the 03:07 / 15:07 Fitter cycle stays SHIP. Do NOT refit biases mid-trajectory ([[feedback-read-inline-rules-before-editing]]).

Watch the L5 row in the debug page's S1 audit table. Do NOT refit biases mid-trajectory ([[feedback-read-inline-rules-before-editing]]).

## Historical: state at 2026-06-21 (post-refit)

L5 promotion-gate gate continues to read **FLICKER (SHIP=1, HOLD=6)**. The clean improving trajectory described on 06-19 has plateaued/regressed.

simulate_windows.py 7-day breakdown today:
```
06-15  HOLD   -5.4%  1/8 regimes  n=24,233
06-16  HOLD   +2.2%  4/8          n=24,307
06-17  SHIP   +7.2%  6/8          n=23,575
06-18  HOLD   +4.6%  5/8          n=21,715
06-19  HOLD   +1.7%  4/8          n=22,237
06-20  HOLD   +2.8%  4/8          n=22,943
06-21  HOLD   +2.6%  5/8          n=20,247
```

The 06-18 / 06-19 cutoffs flipped HOLD on this read vs SHIP on the 06-19 read — same data, two days later — meaning the trailing-window improvement that read as SHIP back then has now thinned. Range today is -5.4% → +7.2% (vs -17.7% → +8.0% on 06-19). Improving direction held but ceiling dropped.

Implication for 06-25: 7-of-7 SHIP gate is **not on track**. Today is 06-21 with 1×SHIP. Even if every remaining day (06-22 through 06-25) returns SHIP, the trailing window at 06-25 will still include the 06-19, 06-20, 06-21 HOLDs. Earliest plausible promotion under current performance is mid-July.

## Late 06-21: L5 bias refit (v0.6.168)

Re-ran `l5_recompute_biases{,_hourly}.py` and patched solar_correction.py with refreshed tables (last fit was 06-17 v0.6.112). Largest fallback shifts: frontal -169.2 → -81.1, se_flow -27.3 → -114.9. simulate_windows verdict moved:
```
Pre-refit:  1×SHIP / 6×HOLD   (ceiling +7.2%)
Post-refit: 3×SHIP / 4×HOLD   (ceiling +8.1%)
```
06-18 and 06-21 flipped HOLD → SHIP. 06-19 (+4.2%) and 06-20 (+5.9%) now within 1pp of the SHIP threshold. Still FLICKER, still NOT promoting. But trajectory direction is good and the mid-July estimate may shorten if the next few daily reads hold or improve.

Re-evaluate daily. Refit again only when the next promotion window opens (don't churn biases mid-trajectory or simulator reads become uninterpretable).

Where the wins are (today's run, realistic regime classification from model forecast):
- nw_flow -46.2%, sw_flow -28.8%, pre_frontal -25.3%, calm -19.7%, frontal -18.8%
- Hurts: sea_breeze +20.1%, ne_flow +17.3%
- se_flow ≈ flat (-1.1%)

## Decision: hold, next gating read 2026-06-25

Why: the earliest 06-13 → 06-15 HOLD reads are still inside today's 7-day trailing window. They roll out on 06-20, 06-21, 06-22. Pure-SHIP territory begins 06-25 if the trend holds (and only if 06-20 → 06-25 all come back SHIP).

Concrete decision points:
- **2026-06-20 to 06-24**: monitor simulate_windows.py output once per day; record SHIP/HOLD
- **2026-06-25**: third hard gating read. If 7-of-7 SHIP → flip `solar_correction.ENABLED = True`
- **Any HOLD day in between**: reset the count; next gating read is now (HOLD_date + 7)

If we flip on, expect heavy benefit in nw_flow / sw_flow / pre_frontal hours, and accept the cost on sea_breeze (where L5 is currently making things 20% worse — that regime's signal isn't there yet, may need its own future hypothesis).

## Supersedes

- [[project-06-18-session]]: the "L5 HOLD verdict on 06-18T03:07" line was a point-in-time snapshot using the realistic_regime path; tonight's same-script run with a different cutoff was SHIP. The bigger truth is the trajectory, not any single point. Don't act on the snapshot.
- [[project-06-08-to-06-22-plan]]: the 06-22 L5 third-read date is no longer correct. Real next date is 06-25.
- [[feedback-hypothesis-promotion-pipeline]]: L5 is at Stage 1 (curated text). Stays Stage 1 until 7-window gate passes.

Related: [[project-correction-stack]], [[project-walkforward-l3l4-validator]].
