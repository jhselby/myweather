---
name: project-stage4-audit
description: C1 Stage 4 UI-readiness audit built 2026-06-24 v0.6.216. analysis/c1_stage4_audit.py. Legacy axis NOT READY (pp/pa drag); multi-axis DEFERRED until ~2026-07-04 (cluster_spread log retention).
metadata: 
  node_type: memory
  type: project
  originSessionId: a933ef0e-f53e-46b4-802a-0d1b833732d0
---

## What it is

`analysis/c1_stage4_audit.py`. Compares each curated SHIP cell's calibrated MAE against its realized MAE on a 7d recent-holdout window vs a 7d preceding calib window. Two views:

- **Legacy axis**: per-(field, band, stable|transition) cells from the top of the curated table. 62 SHIP cells. Always auditable from the pair log alone.
- **Multi-axis**: per-(field, band, axis_key) cells where `axis_key = Q::pt::trans::c1f` (the v3 4-axis cells). 296 SHIP cells. Needs `cluster_spread_log.json` to reach back into the calib window.

Drift verdicts: PASS ≤20%, WATCH ≤40%, FAIL >40%. Overall recommendation:
- ≥80% PASS + ≤5% FAIL → "READY — flip ENABLED=True after one more weekly confirmation"
- ≥60% PASS → "MIXED — most cells stable but tail unstable; hold"
- otherwise → "NOT READY — drift exceeds tolerance on majority"

Output: `analysis/output/c1_stage4_audit.json` plus stdout summary with top 5 worst drifters.

## First-read verdict (2026-06-24)

- **Legacy: NOT READY.** 17 PASS / 20 WATCH / 25 FAIL of 62. Top drifters are ALL `pp` (POP, Brier-evaluated — MAE is the wrong yardstick by design) and `pa` (precip amount, naturally bursty). Examples: `pp/24-47h [stable]` drifted +3447%, `pa/0-5h [transition]` drifted +2154%. Non-precip subset (t, h, ws, wg, cl, cm, ch, sr, pr) would likely pass cleanly — worth a follow-up audit with `pp` and `pa` filtered out.

- **Multi-axis: DEFERRED until ~2026-07-04.** `cluster_spread_log.json` only goes back to 06-20 (~4 days); the audit's calib window starts at now-14d = ~06-10. Every multi-axis pair gets `spread_q=None` and is skipped. First useful multi-axis read comes ~10 days later as cluster_spread accumulates.

## Why this matters

Without a passing Stage 4 audit, `confidence_layer.py::ENABLED` stays False. The C1 bands stamp into `weather_data["confidence"]` every tick but the UI doesn't treat them as authoritative. Flipping ENABLED is the user-visible go-live for C1.

The discipline: don't flip ENABLED until the audit has at least one PASS verdict on each view (legacy + multi-axis). MARGINAL cells are excluded from Stage 4 by design — only SHIP cells get audited.

## Known footguns

- **MIN_N_CELL was 30 initially** (matching Stage 1's MIN_N_MULTI floor on a 14d window), too tight for the 7d audit windows. Halved to MIN_N_CELL=15 on the second run. Even at 15, every multi-axis cell came back INSUFFICIENT — the real bottleneck was cluster_spread retention, not pair-log density.
- **Marginalization vs conditioning.** Audit uses the same SHIP cells the curated table classified, so this isn't a concern here, but a related ortho pattern bit me twice today (see [[feedback-orthogonality-gate]]).
- **POP and precip amount are Brier-evaluated and bursty respectively.** They will drag any MAE-drift verdict. Stage 4 audit honestly reports them, but the next iteration should expose a per-field-class subset (precip-only vs non-precip-only) on the verdict so the user can see whether the non-precip half passes independently.

## Next actions

- **Run a non-precip-subset audit** (one-line filter): a quick check of whether t/h/wind/cloud cells alone earn READY today. Could greenlight a partial ENABLED.
- **~2026-07-04**: re-run audit. By then cluster_spread reaches the calib window and the multi-axis verdict becomes meaningful.
- **Weekly cadence after that**: the audit becomes a standing manual run alongside walk-forward L3/L4. If 2 consecutive weekly reads show legacy READY + multi PASS, flip ENABLED=True.

Related: [[project-c1-pivot-to-confidence]], [[project-06-24-session]], [[feedback-hypothesis-promotion-pipeline]], [[feedback-whitelist-promotion-gate]].
