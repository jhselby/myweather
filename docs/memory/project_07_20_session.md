---
name: 07-20-session
description: "2026-07-20 Mon marathon: 8 ships. Morning findings (v0.6.365-365d): divergence LSR fix, wd first-class in analysis surface, L3 asymmetric Stage 1, cc-sat killed. Afternoon (v0.6.366-368b): L3 asymmetric wg wired, Fitter surface for wd, wd L2 blend live, debug sweep."
metadata: 
  node_type: memory
  type: project
  originSessionId: d0ce8e13-443e-4221-9625-a6ecbc9e587f
  modified: 2026-07-20T18:36:01.905Z
---

# 07-20 Session (Mon) — 8-ship marathon

Started as digest-review day (0 new SHIP-eligible after false alarms). Turned into three novel Stage 1 findings by noon (one killed same-day), then afternoon shipped one full L3 refactor + all wd plumbing to first-class + a real L2 blend for wd.

## Shipped commits (all pushed to origin)

**Morning batch (analysis + prep):**
- **v0.6.365** — divergence LSR bug fix + 3 Stage 1 scripts + wd_persistence_gate processor drafted
- **v0.6.365a** — cc-sat correction KILLED same-day (rediscovery of Lc)
- **v0.6.365b** — wd promoted to first-class in anomaly_detector + h_persistence_skill
- **v0.6.365c** — debug page Rule 5 sweep for morning ships
- **v0.6.365d** — wd first-class in accuracy chart + pipeline table + mae_over_time

**Afternoon batch (real corrections):**
- **v0.6.366** — L3 asymmetric fc-bin skip machinery wired for wg (48 SKIP cells live)
- **v0.6.366a** — debug page Rule 5 sweep for v0.6.366
- **v0.6.367** — joiner emits per-layer wd errors (`error_l1..error_l4`) circularly; Fitter now scores wd
- **v0.6.368** — wd added to L2 in wind_blend.py (had field-name bug)
- **v0.6.368a** — wd L2 blend hotfix (`cur.get("wind_dir")` → `cur.get("wind_direction")`)
- **v0.6.368b** — debug page Rule 5 sweep for v0.6.367 + v0.6.368/368a

## wd went from raw-only to full first-class

Before session: wd was raw HRRR only, all-null in `per_layer_mae_by_lead["wd"]`, absent from WINNING FIELDS tile, no correction candidates, no L2/L3/L4.

After session:
- L2 blend live (circular sin/cos unit-vector, 24h linear decay, calm floor 3 mph) — see [[wd_l2_blend]]
- Fitter emits per_layer_mae/rmse/bias for wd via joiner fix + circular_diff
- Accuracy chart shows wd (dropdown + raw+L2 series)
- Pipeline table wd row updated
- anomaly_detector, h_persistence_skill, mae_over_time all circular-aware
- wd_persistence_gate Stage 2 processor drafted, ENABLED=False, gate started counting 07-20
- 14-day post-ship watch through 08-03 for wd L2

## Key architectural moment

Joe corrected two of my instincts mid-session:

1. **L2 additions don't need Stage 0→3 gating.** L2 is architectural (obs blend). Only L3/L4/specialists need the promotion pipeline. See [[feedback_l2_no_stage_gate]].
2. **L2 IS the observation, not just a forecast layer.** The consensus that becomes L2 also feeds obs_temp_log; same value, two consumers. Circularity in measurement is known + accepted; removing L2 from pipeline was previously rejected as too costly. See [[project_l2_as_observation_only]] (updated).

For wd specifically, v0.6.368 REDUCED cheating: previously wd's obs_temp_log value came from `hourly[0]` which was raw fc = worthless. Now h=0 = 100% obs consensus = real observation.

## L3 asymmetric fc-bin — machinery landed

Extended `decay_apply.py`'s SKIP_TABLE with an asymmetric fc-bin dimension via a parallel `SKIP_TABLE_ASYMMETRIC` path. Loads curated JSON per (field, layer), bins raw fc via `hourly["raw_wind_gusts"]`, skips L3 when `(regime, band, fc_bin)` ∈ SKIP set. wg wired live (48 cells). ws deferred — its blanket hardcoded skips (`ne_flow` all, `sea_breeze 0-11`) disagree with asymmetric grid at those cells; replacement waits for 7-window whitelist promotion gate. Earliest ws swap 07-27.

## Session lessons banked
- [[feedback_l2_no_stage_gate]] — L2 additions skip the promotion pipeline
- [[feedback_divergence_claim_mismatch]] — live-gate flags source from live gate history
- [[feedback_measure_against_live_stack_baseline]] — pair log `forecast`/`error` are L1 semantics

## Live workstreams (heading into next session)

### wd L2 blend — 14-day post-ship watch through 08-03
Trigger: any spurious wd swing on wind card at short-lead, or `per_layer_mae_by_lead["wd"]["l2"]` flipping worse than `l1` once n>100 per lead (~1 week). Calm-floor guard (3 mph) is the top failure risk.

### wd persistence gate — earliest flip 07-27
Now the SECOND wd correction candidate (L2 covers short-lead; this targets long-lead regime-transitions). 5 SHIP + 1 MARGIN cells. Wiring plan: applied_layer stamping in `forecast_snapshot.py:207-208` currently skips wd — needs a `wdp` layer alongside `chp`/`clp`. Same 4-site checklist as [[feedback_specialist_attribution_wiring]]. See [[wd_persistence_gate]].

### L3 asymmetric ws swap-in — earliest 07-27
Once whitelist gate clears, replace `SKIP_TABLE[("ws","l3")]` blanket entries with asymmetric grid. See [[l3_asymmetric_fc_bin]].

### Other pending
- pre-frontal Stage 3 wire — day 1/7 07-19
- C1 Stage 4 next window — 07-25
- sr Lsb halves re-run — 07-24
- wg residual persistence gate — 07-21 flip candidate
- wg L3 skip-table (regime × band, separate from asymmetric) — 07-21 flip
