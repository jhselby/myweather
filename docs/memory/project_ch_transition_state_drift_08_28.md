---
name: ch-transition-state-drift-08-28
description: "Stage 4 REAL DRIFT finding 2026-08-28 — ch 6-11h in transition state is a \"corrections make it worse\" cell. Investigation queued."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8c047e09-3a34-4078-b6a2-c36aecb5ff73
  modified: 2026-08-29T10:37:26.739Z
---

**Finding (Stage 4 difficulty lens, 2026-08-28):**

- `ch/6-11h/transition`: Prod MAE 24.9 → 25.5 (**+2.3% worse**) while Raw MAE improved 18.2 → 15.4 (**−15% better**). Ratio −6.58× — Prod moved in the *opposite* direction from Raw. This is 1 of only 3 REAL DRIFT cells in the whole audit; the other 2 (wg cells) are already covered by curated skip cells.
- n=468 → 294 rows (calib → recent), so not thin. Signal is real.

**Interpretation:**

Something in the ch correction stack (L2 KBOS+KBVY blend / L3 lead-decay / L4 diurnal / chp persistence gate) is applying calibrated-for-stable-regime bias to transition-state rows and actively hurting the forecast on the 6-11h band. Raw got better because the underlying model handled the recent regime shifts; Prod got worse because the corrections drift when the state changes.

The chp gate table is keyed on `(regime_synoptic, lead_band)`, no `state_fc` cross-cut. Same for L3 SKIP_TABLE. So there's no existing mechanism to suppress ch corrections during transition state at 6-11h.

**Why:** transition-state rows are inherently harder — the atmosphere is shifting. Stable-regime bias tables misfire. The gap here (Prod worse, Raw better) is diagnostic of exactly that failure mode.

**How to apply:** Investigate next session with these questions in order:
1. Is the +2.3% Prod-worse mostly from one layer (L2 vs L3 vs L4 vs chp)? Per-layer MAE walkforward at (ch, 6-11h, state_fc=transition) would answer.
2. If it's chp: does the chp gate already fire less often in transition, or does it just apply the same? Add a state-conditional skip.
3. If it's L2/L3/L4: consider a state_fc-cross-cut in the existing skip table (would need a new column added to `weather_collector/data/skip_table_curated.json`).

**Related:** [[project_ch_chp_regression_watch_08_13]] (2nd emergency chp demote), [[project_ch_persistence_gate_ship]], [[feedback_scoreboard_vs_cell_aggregation]], [[project_stage4_audit]].

**08-29 CLOSED — did not replicate.** Today's Stage 4 lens: Prod 13.65 → 11.90 (-12.8% BETTER), Raw 28.17 → 33.44 (+18.7% worse), ratio -0.68, tag `small — ignore`. Yesterday's REAL DRIFT tag was one-day noise, not a stable failure mode. No investigation needed.
