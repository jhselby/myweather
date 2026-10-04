---
name: feedback-top-level-forecast-is-l2
description: "Pair log top-level `forecast`/`error` are L2-semantic BY DESIGN, not Production. Analysis scripts scoring Production must reconstruct from `forecast_{applied_layer}`."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b5cc4ed2-5f65-4bf9-8d07-bd839cb57caa
  modified: 2026-08-17T12:05:35.401Z
---

The pair log's top-level `forecast` field equals the L2 value, not the applied/user-visible value. Set explicitly at `forecast_snapshot.py:246-249` — the Fitter reads top-level as "the forecast" and calibrates decay coefficients from `(forecast - obs)`; if top-level were post-decay, the Fitter would see ~0 error and decay corrections would shrink to zero. This is load-bearing for the Fitter and must not change.

**Consequence:** any analysis script that treats top-level `forecast`/`error` as "Production" is scoring L2, not Production. For fields where L2 == L1 (ch, cc, cl, cm — no decay applies to clouds), this scores raw L1 as Production and every L3/L4/L6/specialist contribution is invisible.

**Why (concrete history):** discovered v0.6.390y when investigating `h_persistence_skill.py`'s "ch: L4 -0.26 → Prod -1.31 (Δ -1.06)" line. Turned out chp was working fine — the script's `mae_prod = mean(|top-level error|)` was measuring raw L1 error. Sample chp-applied row: `forecast_chp=6.0, error_chp=0.0` (perfect) but `forecast=0.0, error=-6.0` (L1). Same class of silent-lie as [[feedback_shadow_write_applied_layer_trap]], [[feedback_l1_only_field_routing_trap]], [[feedback_pair_log_error_field]].

**How to apply:** in any analysis script computing "Production" MAE/skill from the pair log, use the shared helper:
```python
from _prod import prod_error   # analysis/_prod.py
err = prod_error(row)          # None if no layer error present
```
Or, if you need the forecast value not the error, reconstruct as:
```python
applied = row.get("applied_layer")
fc_prod = row.get(f"forecast_{applied}") if applied else None
if fc_prod is None:
    fc_prod = row.get("forecast_l4", row.get("forecast"))  # last-resort fallbacks
```
Never treat top-level `forecast` / `error` as Production without the reconstruction. Only the Fitter's decay-calibration path is allowed to consume the raw top-level value.

**Digest sweep completed 2026-08-17.** 20 analysis scripts converted (5 production-visible metrics + 15 hypothesis Stage 0/1/2 signal tests). The one that mattered most in real triage: `anomaly_detector` previously reported cm CLEAN when real prod was WATCH +32.6%. Post-fix output now matches morning reality. `decay_tau_tuning` and `mae_over_time`'s wd L1_ONLY fallback are the only remaining reads of top-level `error` — both correct usages (decay calibration + wd pre-v0.6.368 raw fallback).
