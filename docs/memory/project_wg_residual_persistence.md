---
name: wg-residual-persistence
description: "07-14 v0.6.351 Stage 3 wired ENABLED=False. Stage 2 per-cell verification: 6 SHIP / 30 SKIP / 1 THIN of 37; all SHIPs long-lead (12-23h + 24-47h) in flow regimes (frontal/pre_frontal 24-47, se_flow 12-23+24-47, sw_flow 12-23+24-47). Every 0-5h + 6-11h SKIPs everywhere — L2 already tracks recent obs close-in. Correction = fc_l2 + prior-14d L2-residual mean at same clock hour, 24-slot per-hour table refit weekly in same JSON as cell verdicts. Runs AFTER decay_apply. Earliest flip 07-21."
metadata: 
  node_type: memory
  type: project
  originSessionId: 5d8d6cee-65cf-4a8f-b3d2-fa890136f897
  modified: 2026-07-20T23:07:07.143Z
---

## Ship timeline

- **v0.6.342 (07-13):** Stage 0 novel finding. `analysis/h_daily_residual_persistence.py`. Rolling 2d-mean L2-residual at same clock hour → wg MAE −6.13% held-out; every other field regressed.
- **v0.6.343/344 (07-13):** Stage 1 preview. Grid over window ∈ {1,2,3,5,7,14}d × baseline ∈ {L2, Production}. Winner window=14d, L2 baseline, pooled MAE +17.04% held-out. First read MARGINAL — halves 18.44/0.49 unstable + calm regime kills −71.29%.
- **v0.6.351 (07-14):** Stage 2 per-cell verification + Stage 3 processor wired ENABLED=False. Pooled +17.04% narrowed to per-cell truth: **only 6 SHIP cells**, all long-lead in flow regimes.

## Stage 2 verdict (07-14, MIN_N_CELL=200, floor=3.0%)

| regime | 0-5h | 6-11h | 12-23h | 24-47h |
|---|---:|---:|---:|---:|
| calm | SKIP +321% | SKIP +226% | SKIP +145% | SKIP +109% |
| frontal | SKIP +61% | SKIP +3% | SKIP −36% (halves flip) | **SHIP −49%** |
| ne_flow | SKIP +47% | SKIP +14% | SKIP −2% | SKIP −3% |
| nor_easter | THIN | | | |
| nw_flow | SKIP +59% | SKIP +18% | SKIP −12% (halves flip) | SKIP −6% |
| pre_frontal | SKIP +42% | SKIP +11% | SKIP −3% | **SHIP −29%** |
| se_flow | SKIP +71% | SKIP +0.5% | **SHIP −19%** | **SHIP −32%** |
| sea_breeze | SKIP +44% | SKIP +32% | SKIP −14% (halves flip) | SKIP −11% (halves flip) |
| sw_flow | SKIP +70% | SKIP +3% | **SHIP −23%** | **SHIP −25%** |
| unknown | SKIP +14% | SKIP +26% | SKIP +24% | SKIP +8% |

**Pattern:** every 0-5h + 6-11h SKIPs in every regime. Long-lead only, flow-regime only. `calm` and `unknown` never ship at any lead. `sea_breeze` never ships (halves flip). `ne_flow`/`nw_flow` never ship (magnitude too small).

## Runtime architecture

**Correction data source:** `weather_collector/data/wg_residual_persistence_curated.json`. Contains both:
- `cells[regime][band]` with verdict per cell
- `hourly_correction.hour_of_day[0..23]` — 24 mph values, mean prior-14d L2 residual per clock hour from most recent pair-log date. Refit every Stage 2 run (weekly cadence in nightly digest).

**Processor:** `weather_collector/processors/wg_residual_persistence.py`. Reads `hourly.wind_gusts_post_l2` (stashed by decay_apply.py:461), looks up `(regime, lead_band)` cell verdict + `hour_of_day` correction, computes `fc_l2 + correction`, overwrites `hourly.wind_gusts` in SHIP cells only. Preserves pre-gate array as `hourly.wind_gusts_post_l3_pre_wgrp`. Sanity clamps |correction| > 15 mph. Placed AFTER decay_apply in collector.py so it overrides L3.

**Wire pattern:** mirrors ch_persistence_gate but with an add-on correction instead of persistence-of-obs replacement.

## Why the pattern

L2's Kalman blend re-fits each tick from recent obs, effectively absorbing residual bias at short leads. Adding a 14-day historical residual mean on top at short leads re-introduces stale bias L2 already corrected. At long leads (12-47h), L2's window is too short and doesn't capture climatological drift — the residual mean fills that gap.

`calm` regime is dominated by rare-event wg spikes that the residual mean can't predict (SKIP everywhere, magnitude +100%+ worse). `sea_breeze` sees enough regime turnover to break halves stability. Flow regimes (se/sw/frontal/pre_frontal) have persistent multi-day patterns the residual mean captures.

## 7-day gate

- Day 1 = 07-14. Earliest flip = 07-21.
- Weekly re-run of `h_wg_residual_persistence_stage2.py` refreshes both cell verdicts and the 24-slot correction table.
- Any halves sign-flip in a SHIP cell demotes it to SKIP.
- Correction magnitudes (currently ~±5 mph diurnal cycle) blowing past 15 mph triggers processor sanity-clamp; refit-fault caught but not aborted.

## 07-20 read (day 7 — fresh Stage 2 re-run at 17:35 EDT)

- **Rollup: 10 SHIP / 4 MARGIN / 22 SKIP / 1 THIN.**
- **07-14 → 07-20 preservation: 5 of 6 originals still SHIP.** Dropped: se_flow 12-23 (Δ full still −10.77% but halves-flip Δ B=+2.61% demotes).
- **New SHIP cells (5):** nw_flow 12-23 (−18.4%), nw_flow 24-47 (−16.2%), se_flow 6-11 (−17.6%), sw_flow 6-11 (−9.7%), unknown 6-11 (−8.9%).
- **Jaccard vs 07-14 baseline = 5 / 11 = 0.45. FAILS the 0.8 narrow-promote gate** ([[feedback-streak-walker-robustness]]).
- Stage 1 pooled reading (informational, not the ship gate): MARGINAL — window=5d +16.84% MAE full-window, halves sign-flip, calm regime loses −30%.

## 07-21 flip decision: HOLD

Do not flip. Map is directionally healthy (5/6 preserved + growth) but churning too fast for a stable ship.

**Path forward:** treat today's 10-cell map as the new baseline. Restart the 7-day clock. **Earliest flip = 07-27** — same day as [[wd-persistence-gate]]'s flip target, coincidentally. If the 10-cell set holds through the week, ship. If it churns again, hold.

No automated streak walker exists for this candidate — divergence_report doesn't cover it, and digest_state emits `no_verdict` because the Stage 2 script prints ROLLUP + PROPOSED GATE SHAPE rather than a `Verdict:` line. Cell-set comparison must be manual each week.

## Comparable magnitude

- ch persistence gate (shipped 07-12 v0.6.327): 22 SHIP / 6 MARGIN / 8 SKIP / 1 THIN of 37. Broad ship map.
- wg residual persistence (this): 6 SHIP / 30 SKIP / 1 THIN of 37. Narrow ship map, long-lead only.

Both are the same "regime-gate-first converts mixed-pooled to clean per-cell ship" pattern; the difference is that ch's L4 fails broadly and persistence wins broadly, while wg's L2 already handles short leads and the residual only adds value where L2's window is too short.

## Related

- [[07-13-session]] — parent session memo (Stage 0/1 ship day).
- [[persistence-skill-baseline]] — wg was MIXED there; this Stage 2 shows why: pooled averages a real long-lead win against a real short-lead noise-add.
- [[feedback-regime-gate-first]] — the architectural frame that made this ship.
- [[ch-persistence-gate-ship]] — analogous prior ship, same frame.
- [[feedback-whitelist-promotion-gate]] — 7-day / halves-verified / no-flip gate governing the 07-21 flip.
