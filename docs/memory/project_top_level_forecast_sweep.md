---
name: project-top-level-forecast-sweep
description: "Open sweep — analysis scripts still reading top-level pair-log forecast/error as if it's Production. Follow-up to v0.6.390y."
metadata: 
  node_type: memory
  type: project
  originSessionId: b5cc4ed2-5f65-4bf9-8d07-bd839cb57caa
  modified: 2026-08-03T12:08:43.031Z
---

Open follow-up from v0.6.390y (2026-08-03), which fixed `h_persistence_skill.py`. Same trap likely lurking in other scripts. Full pattern doc in [[feedback_top_level_forecast_is_l2]].

**Strong suspects (label variables "prod" or "fc_prod" but read top-level `forecast`):**
- `analysis/h_dp_residual_persistence_stage1.py:74` — `fc_prod = r.get("forecast")`
- `analysis/h_wg_residual_persistence_stage1.py:70` — `fc_prod = r.get("forecast")`
- `analysis/pp_brier_reliability.py:81` — `fc_prod = r.get("forecast")` (pp is Brier-only — may be legitimate since pp has no L3/L4 stack; verify before touching)

**Weak suspects (proper L4→L3→L2→L1 fallback chain but missing `forecast_{applied_layer}` reconstruction — will miss chp/clp/wdp/L6/Lsr contributions):**
- `analysis/c1_stage4_difficulty_lens.py:113`
- `analysis/production_regime_trajectory.py:114`
- `analysis/c1_confidence_calibration_v2.py:305`

**Non-suspect (uses top-level intentionally as baseline reference, not "production"):**
- `regime_transition_audit.py:120`, `simulate_windows.py:145` — top-level `error` used as baseline for transition-penalty measurement.
- `mae_over_time.py:178` — L1_ONLY branch already fixed 08-02 ([[feedback_l1_only_field_routing_trap]]).

**Why:** the fixed h_persistence_skill was making ch look like chp destroyed 1.05 skill points; actually chp adds skill. Any of the strong suspects could be hiding a similar false-negative on a specialist. Not urgent — failure mode is "makes specialists look worse than they are," so we already know to be skeptical of Prod-vs-L4 deltas until swept.

**How to apply:** each strong suspect: check what `fc_prod` is compared against. If it's the "did the correction help?" comparison, replace `r.get("forecast")` with the applied_layer reconstruction pattern from [[feedback_top_level_forecast_is_l2]]. Weak suspects: same reconstruction, but the risk is lower (they at least fall through to L4).
