---
name: project-07-28-session
description: "Tuesday 2026-07-28 session. 5 ships (v0.6.383, 383a, 383b, 383c, 384), 5 commits, 2 collector deploys. Digest-triage session pivoted into real R&D + one production behavior change. Marquee: (1) sr L2 unit-mismatch resurface caught + suppressed in analysis scripts + l5_solar registry backstop. (2) h_dewpoint_depression extended with t/dp attribution split — cleared 5-week-stale backlog #6 attribution gate; 3 DP-DOMINANT ★ regimes with ~−2°F dp under-forecast. Backlog #7 added. (3) Lsb gate narrowed cc<25 only after overcast half regressed — narrowed shape PROMOTES; fresh 7-day gate; deployed. (4) Debug page sweep. (5) **v0.6.384: wind_blend BLEND_HOURS shrunk 24 → 4 as root-cause fix for the ws +30% Prod-vs-Raw regression that had run for 2 weeks.** Investigation path: Joe raised 'overall MAE getting worse' → mae_over_time per-field cross-cut → per-lead TSD showed L2 catastrophic at leads 3-16 (L3 was bit-identical, SKIP additive was attacking wrong layer) → new `h_ws_blend_hours_sweep.py` back-solves observed_current per run and sweeps {1,2,3,4,6,8,12,24} → BLEND_HOURS=4 wins at +14.72% pooled MAE, halves +8.4%/+22.4%, every lead-band improves. 14-day post-ship watch."
metadata: 
  node_type: memory
  type: project
  originSessionId: f625f9ff-cf4b-4735-b4d3-d0baee6f3c2f
  modified: 2026-07-28T13:07:49.662Z
---

## Session shape

Started as digest-triage sweep and turned into a real productive day. Three rule-4 violations by me early on ("stumble on it fresh" before greping memory) — corrected each time, but the pattern is worth flagging: on morning digest review, memory-grep FIRST before proposing anything as "new." Documented in `feedback_digest_triage_discipline` already; today reinforces.

## Marquee findings

### 1. sr L2 unit-mismatch resurface (v0.6.383)

Morning digest triage rediscovered the same sr L2 candidate that was investigated and re-scoped 2026-07-06. `l2_lead_decay_fit.py` recommended sr τ=120h (+4.5% MAE held-out); `l2_regime_lead_analysis.py` running stale τ=24h proposed skip-table; `h_full_regime_sweep.py` surfaced 9 sr-L2 ADD candidates.

Verified sr has NO L2 wired in production — `station_bias.py` covers only t/h/pr; `DEFAULT_L2_TAUS` has t/h/pr only; `direct_radiation_post_l2` has no writer; pair-log spot check shows `forecast_l2 == forecast_l1` bit-identical in 20k sr rows. The +4.5% signal is fitting the definitional gap between model `direct_radiation` (direct-beam only) and Tempest `solar_wm2` (total shortwave), not station consensus. Same trap as [[project_sr_unit_mismatch]] 07-06.

Two script patches to prevent re-triage next session:
- `analysis/l2_regime_lead_analysis.py` — TAU_H 24 → 120, docstring rewritten with ⚠ blocker header, verdict emit line now reads "⚠ DO NOT SHIP: blocked by unit mismatch." Re-cut at τ=120h confirmed 0 losses (2 WIN, 30 flat).
- `analysis/h_full_regime_sweep.py` — 5-line filter in `emit()` suppresses sr L2 ADD candidates with pointer to project_sr_unit_mismatch. Rollup: `21 SKIP + 10 ADD` → `21 SKIP + 1 ADD` (remaining ADD is legit sr/L4/pre_frontal 6-11h).

Also `l5_solar_analysis` false-positive → registry backstop: script has been emitting "flip solar_correction.ENABLED = True" every daily digest but `solar_correction.py:46` has been `ENABLED=True` since v0.6.248 (2026-06-28). Added to `KNOWN_LIVE_PIPELINES` in `build_executive_summary.py`.

### 2. h_dewpoint_depression t/dp attribution (v0.6.383a)

Cleared the 5-week-stale promotion-gate blocker on `project_hypothesis_backlog` #6 that had been sitting since 2026-06-24 ("Promote when t/dp attribution is clear AND signal holds").

Extended `h_dewpoint_depression.py` with per-regime t-bias + dp-bias attribution split. Depression bias = t_bias − dp_bias by construction, so classifies each regime T-DOMINANT / DP-DOMINANT / BOTH-COMPOUND / BOTH-CANCEL / NOISE. Reader rule: dp-side correction candidates only ship on DP-DOMINANT regimes; T-DOMINANT would just mask t-bias.

**DP-DOMINANT ★ regimes** (consistent ~−2°F dp under-forecast):
- pre_frontal: t +0.54, **dp −2.14** (n=19,621)
- nw_flow: t +0.27, **dp −2.20** (n=45,589)
- sw_flow: t −0.49, **dp −2.34** (n=20,034)

**BOTH-COMPOUND ★**: frontal (t +1.47, dp −1.63, n=2,232) — model imagines warmer/drier post-frontal airmass than shows up.

**BOTH-CANCEL / T-DOMINANT / NOISE**: everyone else.

Physical read: model systematically under-predicts moisture in shear/turbulent-mixing regimes. Consistent across n=85k rows in the DP-DOMINANT set.

Backlog updates: #6 refreshed with attribution finding + direction-stability watch still open (aggregate dep bias flipped signs across June-July for 3 regimes; unknown whether DP-DOMINANT attribution held across those flips). #7 added for the frontal BOTH-COMPOUND cell's t-bias half — LOW priority until #6 clears.

### 3. Lsb gate narrowed (v0.6.383b)

Decision session. 07-24 halves re-run on original two-sided gate `(cc<25) OR (cc>=75)` showed:
- Stage 1: MARGINAL (pooled +16.75%, halves 1/2)
- Stage 2 per-cc-bin: **0-25 cc = +35.8% SHIP** (n=969, halves +33%/+40%), **75-100 cc = −17.6% SKIP** (n=351, halves +6%/−23%)

Overcast half of the physical hypothesis was wrong. "Thick attenuation missed" — data says model attenuation is actually fine or over-corrected. Cut the loser, kept the winner.

Files touched: `analysis/sr_sea_breeze_lsr_refit_stage2.py`, `weather_collector/processors/sr_sea_breeze_lsr_override.py`, `weather_collector/data/sr_sea_breeze_lsr_curated.json`, `analysis/gate_firing_rollup.py`.

Narrowed-shape Stage 2 re-run PROMOTES: pooled +31.5%, halves +43.8%/+22.7% (both above +10% ship gate), 4/4 lead-bands SHIP. Landed ENABLED=False with fresh 7-day live-layer gate 07-28 → 08-04 per discipline (no live-layer flip on same-day re-derivation).

Collector deployed 12:27 UTC. Verified narrowed-shape telemetry live 12:37 UTC (`cc_gate: {lo: 25.0, rule: "apply iff cc < lo"}` — no `hi` field, correct).

Hour 13 outlier persists (−43% test, n=145, small-sample fit instability). Future work: per-hour SHIP-only Stage 3 refinement if hour 13 stays problematic post-flip.

Shortwave shadow-log infrastructure preserved. Underpins future sr L2 work once unit mismatch resolves.

### 4. Debug page sweep (v0.6.383c)

Post-ships Rule 5 sweep. Multi-site refresh:
- Recent activity: today's 07-28 header + 3 badge bullets for the ships; yesterday rolled from "today" → "07-27"
- sr section (Engineering status): Lsb narrative rewritten from HOLD/HELD language to narrowed-gate PROMOTE story
- sr pipeline row: same rewrite
- Post-ship watches: new Lsb 7-day flip gate entry (day 0/7 through 08-04)
- Calendar: new "Tue 08-04" entry for the Lsb narrowed-gate flip check

Day counters on other watches (Lc 12/14, chp 10/14, wd L2 9/14, ws 9/14) already auto-refreshed elsewhere; not touched.

## 5. wind_blend BLEND_HOURS 24 → 4 (v0.6.384) — ws root-cause fix

Joe raised: "accuracy has gotten meaningfully worse in the last few days from mean MAE < -13% and MAE median more like -9". Pulled `mae_over_time.json` for 14-day trend.

**Overall picture NOT alarming** — today (07-27) mean −12.83%, median −12.08%, better than 5 of the last 7 days. Trough was 07-25 (mean −6.63%, median −0.16%). Oscillating around a slowly-improving baseline.

**BUT per-field ws was genuinely bad:** +30.5% WORSE than raw today, ≥+20% worse for 4 days running, positive every day for 2 weeks except one.

**Root cause via per-lead TSD:** L2 wins only at lead 1 (−21% vs raw), catastrophically loses at leads 3-16 (+40% to +85%). L3 was bit-identical to L2 at every lead — the ws L3 asymmetric SKIP additive from v0.6.370 was attacking the wrong layer. Real problem was `wind_blend.py`'s `blend_observed_into_hourly` bleeding current observed wind into next `BLEND_HOURS=24` with linear decay. Physical: observed current wind at KBVY has more variance than the next-few-hour average — bleeding a point-in-time observation into a 24h horizon imports gustiness/turbulence/calm-variable noise onto a smoothed model signal.

**Fix (v0.6.384):** new `analysis/h_ws_blend_hours_sweep.py` back-solves observed_current per run from low-lead L1/L2 pair (`obs = (L2 - (1-w)·L1) / w`), simulates alternative BLEND_HOURS. Result: **BLEND_HOURS=4 wins at +14.72% pooled MAE, halves +8.4%/+22.4%, every lead-band improves (0-5 +23%, 6-11 +43%, 12-23 +13%).** One-constant edit at `wind_blend.py:78`. Skipped pre-flip 7-day gate because sweep used 7-day window with halves-stability already checked, and current state actively hurts every day. 14-day post-ship watch instead.

Also updated [[project_ws_l3_long_lead_regression]] with the note that the L3 long-lead narrative was partly hiding this bigger L2 blend problem. L3 SKIP additive (26 cells) is doing legitimate edge-case work but was never the main lever.

Also flagged for future session: cm has been losing lift for 5 days (was −40% range early July, now −9%) — cm L4 mixture-check DEGRADED at 12-23h + 6-11h per digest.

## Related

[[project_todo]] refreshed same session. [[project_hypothesis_backlog]] #6 attribution updated + #7 added. [[project_sr_unit_mismatch]] 07-28 update section. [[MEMORY]] pointers refreshed for all three.
