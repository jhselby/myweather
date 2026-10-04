---
name: project-09-19-session
description: 09-19 Sat — 1 diagnostic fix (pr_l2 SHIPPED_CELLS sync); inter_model_spread wire deferred; sr fresh regression seasonal.
metadata: 
  node_type: memory
  type: project
  originSessionId: d4ff154d-a9eb-435b-9633-2ee0e8fabca3
  modified: 2026-09-19T10:49:06.960Z
---

# 09-19 Saturday session — 1 fix, ims deferred

## Ship (analysis-side, no version bump)
- **analysis/pr_l2_regime_lead_retro.py**: SHIPPED_CELLS synced with runtime. Dropped stale `("nw_flow", "6-11h")` — was unwired in corrected_hourly.py:40 on 09-12 (v0.6.590) but the retro's hardcoded SHIPPED_CELLS never followed, causing false AT-RISK alarms in every digest since. Retro's shipped_live JSON flag now reflects reality.

**Why:** stale classification bug per [[feedback_stale_field_classifications]]. Two lists of live cells (runtime `_PR_L2_FIRE_CELLS` vs retro `SHIPPED_CELLS`) drifted after unwire ship.

**How to apply:** any future pr_l2 wire/unwire must update both lists. Band-label format differs — runtime uses `"X-Y"`, retro uses `"X-Yh"`. Not worth a shared-constant refactor for one field; comment in code flags the invariant.

## Deferred — inter_model_spread C1 axis_6 wire
- Was the 09-19 target ship per prior tomorrow-prep.
- Stage 2 today: 31 SHIP (was 33 on 09-12; **2 cells dropped, 3 UNSTABLE — all sr**).
- UNSTABLE cells: sr 0-5h/6-11h/12-23h — ratio-diverged halves (600×+).
- Not tracked by whitelist_streak or Narrow-promote gates section — no automated 7-day walker.
- Blocked on: sr fresh weather regime (see below). Wait for sr help_fresh to climb back, SHIP set to restabilize, then wire.

## sr fresh regression — no action, watch flip
- `sr.l3_nbm` marginal help +17.8% → +1.55% (Δ +16.2pp), n_paired 6285/2731. Still positive.
- Input L2_NBM MAE 51 → 56 = weather harder (regime shift, 3 days from autumn equinox 09-22).
- `sr.l5_nbm HOT` is a duplicate — L5 disabled since v0.6.471, same 42.0/55.0 numbers pass through from L3.
- User impact muted: chosen_prod 42.6 (7d) / 49.7 (24h) — L1 selector routes sr to HRRR in flow regimes where NBM loses (per by_regime table).
- **Watch:** if help_fresh flips negative next digest → time for a regime-conditional L3_NBM SKIP or narrow to calm/ne_flow.
- **If help_fresh climbs back ≥+8%** → seasonal artifact, resume ims wire planning.

## Other digest state
- h/dp τ-suspect fresh-fire day 3/7 — expected, watch through 09-23.
- wd skip-ADDs (ne_flow 12-23h + se_flow 24-47h) walkforward day 3/7 CONFIRMED, 4 to go.
- L4 add wg day 3/7 gated.
- pr L2 gate re-read: MIXED, Jaccard 0.30. Tool recommendation: re-cut ~10-03.
- `h_h_dp_tau_refit` KILL (supersession guard) — protects CLOSED-CLEAN state from τ=3 dp candidate.
- Tomorrow (09-20): dp Stage 2 preview + h_h_residual_persistence Stage 2 preview HOLDs release.
