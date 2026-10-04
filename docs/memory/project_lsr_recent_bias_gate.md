---
name: project-lsr-recent-bias-gate
description: "Follow-on to today's sr regression — build a recent-bias gate for L5 mirroring the Lc gate design shipped v0.6.413."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9a1f61c0-0486-4626-81ae-ca4da37e80cb
  modified: 2026-08-25T11:58:21.105Z
---

**STATUS 2026-08-25: CLOSED CLEAN — HOLD.** 7-day gate closed 08-23; today's rollup shows 9 runs, 8 distinct days, 0 promote days / 8 hold days, promoted-field set STABLE (empty). Verdict: NULL — sr did not clear Stage 1 halves-strict on any day. Shadow-mode gate ran its full window without finding a shippable field. `LSR_RECENT_BIAS_GATE_ENABLED` stays False. Removed from `corrections_debug.html::OPEN_WATCHES`. Reopen only if sr regime bias flips again like the 08-15 event.

Opened 2026-08-15 v0.6.417 after triaging today's sr regression (prod_real +10% vs raw last 24h; bias flip raw −11.88 → prod +38.48). Refit of `_BIAS_BY_REGIME_HOUR` shipped as immediate bleeding-stopper; this project scopes the durable fix.

**Problem**: L5's static `_BIAS_BY_REGIME_HOUR` can't handle regime bias shifts. Historical fit says "add +130 W/m² to nw_flow" — when today's nw_flow forecast is over- instead of under-forecasting, L5 amplifies the error. Exactly the failure mode Lc had before v0.6.413.

**Design (mirror Lc gate)**:
1. New `analysis/h_lsr_recent_bias_gate.py` — mirrors `h_lc_recent_bias_gate.py`. Emits per-(regime, hour) `gate_apply` decision based on whether recent-N-day observed bias agrees in sign + ≥50% magnitude with the historical fit.
2. Runtime table `weather_collector/data/lsr_recent_bias_gate.json` — same schema as `lc_recent_bias_gate.json`: `fields_cleared`, `per_cell` (indexed by regime×hour instead of field×bin), `notes`.
3. `weather_collector/processors/solar_correction.py` grows a `LSR_RECENT_BIAS_GATE_ENABLED` toggle + `_load_gate()` + `_gate_suppresses(regime, hour)` — mirror of the Lc wire.
4. Runtime contract: when `LSR_RECENT_BIAS_GATE_ENABLED = True` AND `sr` in `fields_cleared` AND `per_cell[regime][hour].gate_apply == False`, return `0.0` from `compute_solar_correction` instead of the historical bias. All other cells: existing behavior.

**Extra consideration vs Lc**: L5 skip is regime-at-issue (single tick value applied uniformly to all 48 leads), but pair-log scoring is per-lead `state_fc.regime_synoptic`. Two options:
- (a) Keep the current architecture, gate on issue-time regime (simpler, matches existing skip).
- (b) Make L5 per-lead — compute correction for each lead's state_fc.regime × hour. Bigger change but fixes the "issued in nw_flow, validates in ne_flow" attribution gap.

Start with (a). If per-regime damage attribution suggests the issue-time skip is the wrong gate, escalate to (b).

**Ship pattern**: same as Lc — Stage 1 halves-strict → 7-day per-field clearance streak → wire shipped OFF → toggle flip after clearance. Same anti-scar-tissue design.

**Related**:
- [[project_lc_regime_conditional]] — parent architectural pattern (Lc gate v0.6.413).
- [[project_chp_cell_skip_to_dynamic_gate]] — sibling; another static→dynamic conversion in flight.
- [[feedback_analysis_tools_drift_from_runtime]] — the class-level failure that motivates all three.

**Estimate**: 2 days Stage 0/1 → 3-4 days Stage 1 halves + gate history → 7-day per-field gate → wire (OFF) → flip. ~14 days elapsed, ~4-6 hours active. Same shape as the Lc gate build.

## 2026-08-16 v0.6.420 — Stage 0/1 script shipped

- **New `analysis/h_lsr_recent_bias_gate.py`** — mirrors `h_lc_recent_bias_gate.py`. Per-cell (regime × hour) sign+magnitude gate. Emits `weather_collector/data/lsr_recent_bias_gate.json` + rolling history at `.cache_lsr_recent_bias_gate_history.json`.
- **Day 1/7 seeded.** Today's Stage 1 verdict: HOLD (safe but no gain) — holdout 08-13→08-15 predates today's regime flip. Mechanics verified — sw_flow/11 correctly gated off (hist −428 vs recent −61, ratio 0.14 << 0.5).

## 2026-08-16 v0.6.421 — Stage 3 wire (OFF)

- **`solar_correction.py` gains `LSR_RECENT_BIAS_GATE_ENABLED = False`** toggle + `_load_lsr_gate()` + `_lsr_gate_suppresses(regime, hour)` + suppression check inside `compute_solar_correction()` after the `L5_SKIP_REGIMES` check.
- **Ship-ahead pattern** — same as Lc v0.6.410 → v0.6.413. When the daily gate history accumulates a per-field 7-day clearance for `sr`, flip is a one-line ENABLED=True + `make deploy-collector`.
