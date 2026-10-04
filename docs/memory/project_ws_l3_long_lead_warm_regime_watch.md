---
name: project-ws-l3-long-lead-warm-regime-watch
description: "07-29 h_full_regime_sweep flagged ws L3 at 24-47h in warm-flow regimes (sw_flow, sea_breeze) as clean-halves LOSE at the regime × lead-band aggregate — but the ws_l3_asymmetric_skip fc-bin verdicts on those cells' Q2/Q4 are MARGIN/KEEP because halves are split (older half helps, recent half hurts big). Recent-half degradation pattern across multiple related cells. If it holds another ~7d, natural SKIP verdicts emerge as older half rolls out."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2612e533-b493-4573-96ed-5a4b19d7982c
  modified: 2026-07-29T17:25:54.732Z
---

## The signal (with important caveat)

`analysis/output/h_full_regime_sweep_summary.txt` on 07-29 flagged 3 apparently-uncovered ws L3 cells at 24-47h:
- **ws L3 sw_flow 24-47h** — Δ_A=-5.1%, Δ_B=-12.5%, sweep-impact 117k
- **ws L3 sea_breeze 24-47h** — Δ_A=-13.1%, Δ_B=-30.2%, sweep-impact 32k
- **ws L3 calm 24-47h** — Δ_A=-14.9%, Δ_B=-20.9%, sweep-impact 28k

**CAVEAT — impact is inflated by stale windows.** Sweep windows are A=07-08→07-23, B=06-23→07-08 — **both entirely predate the 07-28 ws_l3_asymmetric_skip ship (v0.6.386) that put sw_flow Q1/Q3 + sea_breeze Q1/Q3 SKIP verdicts live.** In the sweep windows, L3 was firing on Q1/Q3 rows and losing MAE there. Post-07-28 the asymmetric loader in decay_apply.py skips those Q1/Q3 rows. So current-live-loss ≪ sweep-reported loss.

**Residual current-live loss** = Q2 + Q4 halves-split quartiles only, which the SKIP rule (correctly) refuses to ship.

Similar caveat applies to the wg L3 calm 24-47h + sea_breeze 24-47h cells in the same sweep — those Q1-Q3 are now covered by the 07-28 wg L3 asymmetric SKIP ship (v0.6.385).

## Why the SKIP rule correctly refused to ship

Checked the ws_l3_asymmetric_skip fc-bin verdicts on the un-skipped Q2/Q4:
- **sw_flow 24-47h Q2:** MARGIN, Δ_full=+17.2%, but halves A=+1.4% / **B=+34.5%** — recent half hurts hugely, older half nearly flat.
- **sea_breeze 24-47h Q2:** KEEP, Δ_full=+27.3%, but halves **A=-9.5%** / **B=+39.6%** — sign-flipped. Older half helped, recent half hurts massively.
- **sw_flow 24-47h Q4:** KEEP, Δ_full=-0.16% (near-neutral pooled), halves A=+7.9% / B=-18.3%. Sign-flipped opposite way.

The halves-stability rule correctly refuses SKIP verdicts on halves-split cells — that protects against transient noise.

## The pattern worth watching

**Multiple ws L3 long-lead cells in warm-flow regimes show fresh recent-half degradation.** Half B losing +34/+40% while half A neutral or helping is a signature of structural drift in the correction over the last ~15 days. Companion signal: [[project_cm_investigation_07_28]] mixture-check drift on cl/cm transition cells over the same period. Both point at raw-HRRR-side movement making downstream corrections diverge from fit.

## Predictions / what to check

- **Re-run h_full_regime_sweep with a post-07-28 window** to see the true current picture. The 07-29 output is measuring pre-ship state on wg L3 24-47h + ws L3 24-47h Q1/Q3. Expected: those cell aggregates drop to flat, exposing only the residual Q2/Q4 halves-split leakage. That will re-rank the ADD/SKIP leverage board honestly.
- **~08-05 (7d out):** the ws_l3_asymmetric_skip fitter re-cut will drop the older half. If recent-half loss holds, Q2 sw_flow and Q2 sea_breeze at 24-47h will flip MARGIN/KEEP → SKIP naturally.
- **If recent-half loss fades:** the fresh drift was transient, no action needed.
- **Warning if it accelerates:** if another ws L3 warm-regime cell shows recent-half degradation next week (e.g. nw_flow at 24-47h), the correction may be structurally miscalibrated at long lead in general → re-fit warranted.

## Related

- [[project_cm_investigation_07_28]] — same "recent-half drift" pattern on cm/cl mixture-check
- [[feedback_mixture_check_window_semantics]] — 7v7d framing insight
- [[feedback_pooled_n_time_thin]] — why halves-split cells never ship
- [[project_ws_l3_skip_table]] — 07-28 ship covered pre_frontal + frontal at 24-47h
- [[project_ws_l3_long_lead_regression]] — different but adjacent
