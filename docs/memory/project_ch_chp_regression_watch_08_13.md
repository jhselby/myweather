---
name: ch-chp-regression-watch-08-13
description: "chp mid/long-lead regression reopened 2026-08-13 after prior watches closed clean 08-09/08-10. Prod-vs-L6 MAE gap on ch widened monotonically +3.4→+12.7 over 08-06→08-13. Emergency demote v0.6.405: _CELL_SKIP frozenset of 9 (regime, lead_band) cells forced back to L4 (calm/{12-23,24-47}, nw_flow/12-23, pre_frontal/12-23, se_flow/24-47, sea_breeze/{12-23,24-47}, sw_flow/{12-23,24-47}). Source h_ch_persistence_blend_stage2_vs_l6.txt. 14-day watch through 2026-08-27."
metadata: 
  node_type: memory
  type: project
  originSessionId: b48194ef-300a-4d07-b33f-545f9f25c39b
  modified: 2026-08-17T12:05:09.898Z
---

# ch chp regression watch — reopened 2026-08-13

## Trigger

Digging into worry 2 from 2026-08-13 digest review found the exec summary's "L3+specialists visibly moving persistence skill" line was true for Prod-vs-*persistence* baseline but was hiding the Prod-vs-*L6* regression per [[feedback_measure_against_live_stack_baseline]].

Prod-vs-L6 MAE gap on ch, daily:
- 08-06: +3.4
- 08-07: +3.1
- 08-08: +11.2
- 08-09: +3.9  ← chp shipped (though enabled since 07-19)
- 08-10: +6.3
- 08-11: +8.2
- 08-12: +12.0
- 08-13: +12.7

Monotonic widening post 08-10. Prod now ~2× the MAE of L6 on ch.

`h_ch_persistence_blend_stage2_vs_l6.txt` flagged 9 live cells where chp materially loses to L6 on 10-day held-out:
- calm/12-23 Δ +34.26%
- calm/24-47 Δ +34.89%
- nw_flow/12-23 Δ +22.42% (overlaps diurnal skip 10-18 local per [[project_ch_chp_midlead_band_watch_08_10]])
- pre_frontal/12-23 Δ +27.83% (overlaps diurnal skip)
- se_flow/24-47 Δ -0.16% (parity)
- sea_breeze/12-23 Δ +9.71%
- sea_breeze/24-47 Δ -1.84% (parity)
- sw_flow/12-23 Δ +22.80%
- sw_flow/24-47 Δ +30.69%

`gate_firing_rollup` shows sw_flow chp fires at 71% (5447/7661), pre_frontal at 67%, so mid-lead damage propagates to most Prod-visible ch forecasts.

## Why prior watches missed it

- [[project_ch_chp_regression_watch_08_07]] CLOSED CLEAN 08-09 — closed on Δ metric vs Lc, not vs L6.
- [[project_ch_chp_midlead_band_watch_08_10]] CLOSED SAME-DAY 08-10 — diurnal gate shipped in v0.6.401 addressed nw_flow + pre_frontal daytime bias, but did not touch calm, sw_flow, sea_breeze, se_flow.
- Digest exec summary registered `h_chp_midlead_regression VERDICT: STABLE` (that tool measures chp vs Lc), while the sibling `h_ch_persistence_blend_stage2_vs_l6` (chp vs L6) buried its 9-cell warning outside the summary registry. Two tools, two frames, exec summary only reads one.

## Ship — v0.6.405 (2026-08-13)

`weather_collector/processors/ch_persistence_gate.py::_CELL_SKIP` — code-level frozenset. Chose code over JSON edit because fitter regenerates `ch_persistence_gate_curated.json` daily per [[feedback_curated_json_daily_drift]] — JSON demotes would revert in 24h.

`_cell_fires` checks `(regime, band) in _CELL_SKIP` before verdict lookup. All 9 cells now fall through to L4 (chp path skipped entirely; Lc still applies via the L6 stack).

## Watch dates

- 14-day post-fix watch closes 2026-08-27.
- Day-over-day: check `mae_over_time` for ch Prod-vs-L6 gap. Expect it to shrink back toward +3 in 2-3 days as the sw_flow/12-23 + sw_flow/24-47 tick volume comes off chp.
- If gap does NOT shrink within 3 days, the regression is NOT primarily chp — investigate Lc contribution on ch (Lc active on cc/cm/ch per [[project_lc_regime_conditional]]).

## Escalation options if watch fails

1. Widen `_CELL_SKIP` — the vs_l6 tool's THIN cells (7 additional) may become SKIP as sample grows. Reread daily.
2. Field-level kill on chp for ch — set ENABLED=False, chp becomes telemetry-only until re-fit.
3. Root-cause the Prod-L6 divergence in Lc — Lc's shift-table architecture is regime-blind per [[project_lc_regime_conditional]], may be adding damage post-chp.

## 2026-08-16 update — fresh 4-cell signal + dynamic gate shipped

Today's `h_ch_persistence_blend_stage2_vs_l6` shows 7 live cells losing to L6, but only 4 are consistent losses across both halves:
- **se_flow/6-11: +28.7% (worst; A +22.7 / B +52.1)** — NEW cell, not in `_CELL_SKIP`
- se_flow/12-23: +10.2% (A +11.8 / B +8.4)
- sea_breeze/6-11: +6.3% (A +14.0 / B +2.5)
- ne_flow/24-47: +4.2% (A −0.9 / B +14.1, halves diverge)

The other 3 flagged cells (nw_flow/24-47, pre_frontal/6-11, sw_flow/0-5) actually WIN on the full window but fail halves stability — noise, not real regression.

**08-13 fix still working.** All 10 `_CELL_SKIP` cells now show as SKIP verdict under vs_l6 baseline (not flagged as "live losing"). Fix is effective; today's regression is genuinely new cells drifting.

**Do NOT add to `_CELL_SKIP`.** Per [[project_chp_cell_skip_to_dynamic_gate]] anti-scar-tissue rule + escalation-playbook 7-day gate (day 1/7 today). Only exception is >+50% full-window; se_flow/6-11's full is +28.7% (half B alone is +52.1% but that's not the trigger).

**Dynamic chp cell gate shipped v0.6.421 (Stage 0/1 + Stage 3 wire OFF).** New `analysis/h_chp_cell_gate.py` walks per-cell "chp lost to L6 today?" decisions daily; conservative 7-day rule (all 7 days must show 'lose' before gate suppresses). Runtime wire in `ch_persistence_gate.py` with `CHP_CELL_GATE_ENABLED = False`. Day 1/7 today — se_flow/6-11 is on the walker's 'lose' list today but needs 6 more days of consistent loss before the gate flips it off automatically. When it clears, `_CELL_SKIP` can retire in favor of the dynamic gate.

## 2026-08-17 update — day 1/7 of vs_l6 gate

Digest verdict `h_ch_persistence_blend_stage2_vs_l6`: WATCH, 6 live chp cells losing to L6, worst se_flow/6-11 Δ +68.3%. Escalation-playbook counter now at day 1 of 7. `h_chp_cell_gate` walker also at HOLD day 2/7 (no cell has cleared the 7-day all-lose gate).

Also: today's session found the digest's `anomaly_detector` was reading L2 residual not production, so its per-field verdicts on ch (and every other field) were mislabeled. Fixed in the same session via `analysis/_prod.py` sweep. **After the fix**, anomaly detector shows ch CLEAN +4.3% ΔMAE — chp's damage IS surfacing in prod metrics, but not at ANOMALY threshold yet. The +68.3% worst-cell number remains a real signal even though the pooled ch number is calm.

No demote today. Continue watching. If se_flow/6-11 holds >+50% for another 2-3 days AND ch's anomaly-detector ΔMAE crosses +30%, escalate to widening `_CELL_SKIP` OR flipping `CHP_CELL_GATE_ENABLED = True` (whichever cell has cleared the 7-day walker first — probably neither by 08-20).

## Related

- [[project_ch_persistence_gate_ship]] — SHIP 2026-07-19 v0.6.358, 7-day gate cleared.
- [[project_chp_cell_skip_to_dynamic_gate]] — the dynamic replacement; Stage 0/1 shipped 08-16 v0.6.421.
- [[project_ch_chp_regression_watch_08_07]] — closed 08-09.
- [[project_ch_chp_midlead_band_watch_08_10]] — closed same-day.
- [[project_lc_regime_conditional]] — Lc still running on ch, may contribute residual damage.
- [[feedback_measure_against_live_stack_baseline]] — the metric-frame principle this watch violated (closed on wrong baseline).
- [[feedback_curated_json_daily_drift]] — why the demote is in code not JSON.
- [[feedback_scoreboard_before_healthy]] — the exec-summary framing failure that let it pass unremarked.
