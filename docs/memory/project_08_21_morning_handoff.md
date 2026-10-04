---
name: 08-21-morning-handoff
description: "08-21 morning session close — v0.6.450 cc clamp shipped, v0.6.451 L4_NBM shipped, v0.6.452 L5_NBM shipped. Next entry point is L6_NBM."
metadata: 
  node_type: memory
  type: project
  originSessionId: 59e82d06-cdfb-4ebe-9ff9-4ea3ac9e7b83
  modified: 2026-08-21T12:30:46.609Z
---

# 08-21 morning handoff — L4_NBM + L5_NBM shipped; next is L6_NBM

**READ THIS FIRST — this is the entry point for the next session.**

## What shipped this session

- **v0.6.450** — cc l3_nbm >100% clamp. Added domain clamps in `forecast_snapshot._round_for`: percent fields (`pp/cc/cl/cm/ch`) → `[0, 100]`, `sr` → `≥ 0`. Deployed 11:12 UTC, verified 11:17 UTC tick.
- **v0.6.451** — L4_NBM parallel pipeline shadow-live. Mirrors HRRR L4 (hour-of-day diurnal residual), scoped to `L4_NBM_FIELDS = ("cc", "ch")`. Files: `weather_collector/processors/l4_nbm.py`, `analysis/l4_nbm_fit.py`, `weather_collector/data/l4_nbm_curated.json`, wired into `forecast_snapshot.py` after L3_NBM block. Layer registered in `forecast_error_log.py` both branches. `l1_selector_fit._nbm_prod_error` prefers `error_l4_nbm`. Selector substitution picks deepest available NBM layer. Deployed 12:02 UTC, verified 12:07 UTC tick — `cc_l4_nbm`+`ch_l4_nbm` stamped in all 48 hours of snapshot.
- **v0.6.452** — L5_NBM parallel pipeline shadow-live. Mirrors HRRR L5 (regime × hour_of_day solar bias), sr-only. sr skips L4_NBM by design (sr not in L4_NBM_FIELDS). Files: `weather_collector/processors/l5_nbm.py`, `analysis/l5_nbm_recompute_biases_hourly.py`, `weather_collector/data/lsr_nbm_bias_table_curated.json`, wired into `forecast_snapshot.py` after L4_NBM block. `l5_nbm` registered in error_log. Selector substitution: `sr_l5_nbm > sr_l3_nbm`, `cc/ch_l4_nbm > l3_nbm`. `l1_selector_fit._nbm_prod_error` walks `l5>l4>l3`. Deployed 12:22 UTC, verified 12:27 UTC tick — `sr_l5_nbm` stamped (identity to sr_l3_nbm at current regime; only `se_flow` has fallback bias today +286 W/m² off 71 pairs).

**Why:** Plan-of-record calls for one NBM layer per session (backstamp → L4 → L5 → L6 → specialists). Shipped L4 and L5 in one session because both shared the same infra pattern from L3.

**How to apply:** All three are shadow-live — new layer arrays stamp into snapshots, error columns land in pair log, table warms over 30 days as more `error_l3_nbm` and `forecast_l3_nbm` sr rows accumulate. Selector fit will detect NBM-side lift once tables warm.

## Digest highlights from morning run

- 163/163 pass, no ships fire, no regressions.
- SHIP-ELIGIBLE walkforward matched live config → no new ship.
- New WATCH: **cm layer-shape at 0-5h (+13.4%) and 6-11h (+15.3%)**. cm is L3-shipped for long-lead but hurts short-lead. Log as τ-suspect; don't touch yet.
- Anomaly WATCH: dp, pr, t — weather-mixture drift, not fresh regressions.
- Verdict flips (info only): h_hsf orthogonality kill→PROMOTE (THIN 1/7), h_pre_front + h_wind_shift_rate + h_depression all became KILL/REDUNDANT.
- decay_tau_tuning: HOLD (pa, pp at 1/3 streak).

## Next session entry point

**Start here: L6_NBM.** HRRR L6 lives in `weather_collector/processors/cove_correction.py` — regime + sea-breeze × hour_of_day t correction. t-only, applied after L5 (t skips L4 too — t not in HRRR L4_FIELDS).

Same 4-piece build pattern as L4/L5:
1. `weather_collector/processors/l6_nbm.py` — mirror `cove_correction.py`'s apply-time function.
2. `analysis/l6_nbm_fit.py` — mirror whatever fits the HRRR L6 cove table (grep for it in analysis/).
3. `weather_collector/data/*_nbm_curated.json` — empty stub.
4. Wire into `forecast_snapshot.py` after L5_NBM block; register `l6_nbm` in `forecast_error_log.py` layer lists (both); update `l1_selector_fit._nbm_prod_error` chain to `l6>l5>l4>l3`; update selector substitution.

After L6: specialists sweep (chp/clp NBM siblings — wdp NBM already done in v0.6.440 as `wdp_nbm_fired`).

## Cross-cutting gaps still open across the whole NBM cascade

None of these are L4/L5-specific — they're infra that spans all NBM layers, deferred until L6 + specialists finish:

- Skip-table gate (HRRR uses `_should_skip(short, "l4"|..., regime, lead)`)
- Per-field correction cap (HRRR uses `CAPS.get(short)`)
- Staleness gate on `fitted_at`
- Gate-firing telemetry (`gate_firing_log.record_firing`)
- Config-override plumbing for backtest A/B
- History JSON per refit
- User-visible PWA writeback path — the selector's `entry[f] = ...` writes into snapshot dict, not into `hourly[array_name]`. Same status as L3_NBM today. Joe verified last session that "cc all leads → NBM" flipped user-visible somewhere; the exact write path hasn't been traced. Confirm before assuming parity.

## Files touched today

- New: `weather_collector/processors/l4_nbm.py`, `weather_collector/processors/l5_nbm.py`, `analysis/l4_nbm_fit.py`, `analysis/l5_nbm_recompute_biases_hourly.py`, `weather_collector/data/l4_nbm_curated.json`, `weather_collector/data/lsr_nbm_bias_table_curated.json`
- Edited: `weather_collector/processors/forecast_snapshot.py` (imports + apply blocks + selector substitution), `weather_collector/processors/forecast_error_log.py` (2 layer-list lines), `analysis/l1_selector_fit.py` (`_nbm_prod_error`), `index.html` (version pill), `docs/CHANGELOG.md` (three new entries)

## Feedback caught this session

Joe pushed back sharply on my use of jargon "cross-cutting scaffolding" without defining it, and on my tendency to answer a "are we done?" question with a menu of gaps instead of a direct yes/no. When Joe asks "are we caught up on X?", answer yes/no first, then the reason — don't lead with the list of remaining work unless it's L4-specific. See [[feedback-answer-direct-first]].

Related: [[nbm-parallel-pipeline-plan]], [[08-20-evening-handoff]].
