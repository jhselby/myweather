---
name: 08-28-session
description: 2026-08-28 Fri — scheduled NBM skip-review day. Three ships (v0.6.513–515) landed clean; native NBM L2 root-cause bug found and fixed (was silently broken since 08-26).
metadata: 
  node_type: memory
  type: project
  originSessionId: 8c047e09-3a34-4078-b6a2-c36aecb5ff73
  modified: 2026-08-28T11:52:15.574Z
---

# 08-28 Fri session

**Product state at close:** Three ships in one day, biggest was a silent-2-days-broken production bug fix.

## Ships (all verified end-to-end from GCS pair log)

- **v0.6.513 — NBM skip-proposals scheduled review.** Sustained-7d window fully post-backstamp for the first time today (08-19 refit + 7d + 1d buffer). Of 41 L3_NBM proposals: 19 moot (field not in L3_NBM_FIELDS), 8 wg + 2 ch already curated 08-26 v0.6.500 (**validation: all 8 still on today's list at similar magnitude → 08-26 batch was correctly-aimed**), 4 cc excluded by design (Ccd overwrite). **Net-new: 2 h `se_flow` cells** added to skip_table_nbm_curated.json — `[se_flow, 0, 6]` (−17.8% n=247) and `[se_flow, 24, 48]` (−25.9% n=477). The wait was worth it: it validated the 08-26 batch didn't ship warmup noise.

- **v0.6.514 — native NBM L2 precompute — CRITICAL FIX.** `forecast_snapshot.append_forecast_snapshot()` referenced `weather_data` in two spots inside the native-NBM-L2 precompute block but the function has no such parameter. Silent NameError every tick since v0.6.499 (08-26), catch-all falling back to identity passthrough for all 8 NBM-scope fields. Was hidden until v0.6.512 (08-27) added `import logging`. Fix: added `hyperlocal=None` param, line 250 → `hyperlocal or {}`, line 299 → `current or {}` (current was already a param). Post-deploy verification: all 9 `_l2_nbm` fields (t/h/dp/ws/wg/wd/cc/ch/sr) populated with real corrections. **This means the "native L2 shipped 08-26" claim was architecturally true but not actually running in production for 48 hours.**

- **v0.6.515 — L4_FIELDS drop cc.** 7-day drop gate cleared. `L4_FIELDS = {"ch"}` (was `{"ch", "cc"}`). cc is Ccd-overwritten downstream so this is code-hygiene deadweight, zero user-visible change. Post-deploy verification: `cc_l3 == cc_l4` (both 72); pre-deploy they diverged (cc_l3=53 → cc_l4=46 was a real −7pp diurnal). NBM-side `cc_l4_nbm` untouched (uses separate `L4_NBM_FIELDS`, still active).

## Also settled this session

- **Digest triage:** 170/170 pass. 3 HOT sentries — `sr.l5_nbm` (self-clearing from 08-25 kill), `ch.chp_nbm` (shadow-write per 08-27), `cc.l4_nbm` (NEW — see [[cc-l4-nbm-watch-08-28]]).
- **Scoreboard triage:** 7d STRONG on ch +65% / cm +41%, GOOD on cc +6.6% / t +2.3%. dp verdict REGRESS −65% is derivation artifact only ([[dp is derived]]). h/ws/wd/sr REGRESS is selector picking HRRR while NBM raw wins this week — consistent with 30d fit being 29/30 pre-native-L2 (self-heals now that v0.6.514 shipped).
- **NBM skip-review methodology decision:** The old 08-21 memo said "compare to 08-21 baseline list." The 08-25 revision reframed to "wait for sustained-7d post-backstamp." Today's list *is* the durability signal. No two-list comparison needed.
- **08-28 holds — 4 items reviewed and held** (see [[08-28-holds-reviewed]]): l6_nbm DROP t (THIN), wdp_nbm DROP wd (THIN), h_lc_recent_bias_gate PROMOTE (per-field streak 1/7), l6_fix_b_refit (6 HOLD days).
- **Stage 4 REAL DRIFT investigation queued** — 1 of 3 REAL DRIFT cells (ch/6-11h/transition) is a genuine "corrections make it worse" finding, not weather-mixture. See [[ch-transition-state-drift-08-28]].

## Debug page sweep

- dp and h Status column entries corrected: stale `_L2_NBM_DELTA_SKIP` narrative replaced with v0.6.499 native-L2 endpoint. sr entry left in place (sr remains the only member of `_L2_NBM_IDENTITY`, that claim still holds).
- Recent activity block rolled: 08-28 prepended, 08-27 → 1 day ago, 08-26 → 2 days ago, 08-25 hidden (trimmed to CHANGELOG).

## Product state at close

- 7D Total Lift median +0.2% (yellow zone under new ±2% band from 08-27 v0.6.510).
- Native NBM L2 first-tick-ever landed 11:12 UTC today. Selector fit will self-heal over ~30d as the window rolls past the 08-26 → 08-28 identity-passthrough period.
- Selector Skill still lagging on h/ws/wd/sr — expected.
