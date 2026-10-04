---
name: 08-27-session
description: "2026-08-27 Thu morning session — clean digest triage, three \"HOT\" sentries all resolved as non-actionable (transient DNS, stale-signal, shadow-write); v0.6.510 tile yellow band tightened ±3% → ±2%"
metadata: 
  node_type: memory
  type: project
  originSessionId: ce47e518-fc0a-42dd-8729-c179ac0dae40
  modified: 2026-08-27T14:09:44.061Z
---

# 2026-08-27 (Thu) session

## Headline
Clean triage day. Digest looked scary at open (3 FAILs, 2 HOT sentries, +1 WATCH, big NBM skip-table). None was actionable. One small ship: v0.6.510 tightened scoreboard yellow band ±3% → ±2%.

## What the digest surfaced vs what it actually meant

- **3 fitter FAILs** (l1_selector_fit, l3_nbm_fit, l4_nbm_fit): identical root cause — transient DNS failure resolving `data.wymancove.com` when fetching `forecast_error_log_backstamped.jsonl`. Reran all three manually, wrote fresh curated JSONs. Not a code bug. `l5_nbm_recompute_biases_hourly` hit the same error but has a fallback path so completed OK.

- **sr.l5_nbm HOT +60.3%** (sust 109.7 → fresh 175.9): **stale-signal**. Layer was killed 2026-08-25 (v0.6.471, ENABLED=False in l5_nbm.py). Correction function returns 0.0 when disabled, so sr_l5_nbm is stamped as sr_l3_nbm + 0. The MAE gap is from pair-log rows straddling the kill window (fresh 3d includes pre-kill data with large fallback biases still applying). Will decay out in ~1 more day. No action.

- **ch.chp_nbm HOT +44.6%** (sust 6.23 → fresh 9.01): **shadow-write signal**. chp_nbm curated table is healthy (25 SHIP cells, 30-80% MAE improvement vs baseline in training). But ch L1 selector picks HRRR at every band (30d fit lifts -57% to -149% in HRRR's favor). chp_nbm value gets stamped for pair-log attribution but never surfaces to user-visible ch. Also: fresh MAE 9.01 is BELOW every cell's training baseline (15-33); +44.6% is arithmetic on small numbers. Walkforward proposes exactly one small skip cell (sw_flow 6-11h -4.1%), not layer-wide. No action.

- **cc.l4_nbm WATCH +12.5%**: layer is early-life (shipped 08-21 v0.6.451), sustained window still thin. Walkforward has not flagged any cc l4_nbm cells for SKIP. Prod cc is derived via Ccd anyway, so l4_nbm only affects the selector's cc pick. No action.

- **24H Selector Skill median -12.6% (red)**: losers h·ws·wd. Diagnosed as regime-mix noise. Over 30d, HRRR-Prod crushes NBM-Prod on those fields (HRRR wins by 22%-120% on h, 6%-52% on ws). 24h window happened to hit rows where HRRR-Prod ran worse than NBM-Prod on those fields — normal variance at n≈3.6k per band. 7D median still +2.3% green. No action.

- **NBM walkforward divergences**: `l3_nbm: ADD dp,wd; DROP wg` · `l5_nbm: DROP sr` (already done via ENABLED=False) · `l6_nbm: DROP t` (scaffold ENABLED=False) · `wdp_nbm: DROP wd`. 08-28 scheduled review deferred per calendar (post-backstamp).

- **NBM skip-table proposals**: ~40 cells hurting on l3_nbm plus catastrophic l5_nbm sr entries. Skipped — sr.l5_nbm entries are historical (layer off); l3_nbm review lands 08-28 per calendar.

## Ship: v0.6.510 — scoreboard yellow band ±3% → ±2%

Joe asked "how did you arrive at 5%?" for the tile yellow band. Answer: it's actually ±3%, not ±5%. Grepped `_cls` functions in `corrections_debug.html` and `VERDICT_GOOD_LIFT`/`VERDICT_REGRESS_LIFT` in `analysis/scoreboard_v2.py`.

Origin: ±3% was chosen to match other symmetric watchdog thresholds on the debug page (disabled-layer / enabled-layer band checks), not derived from a noise model.

Empirical noise-floor estimate for a 7d median lift:
- Well-behaved field (t): MAE ~5°F, n ~5,000 paired 7d obs
- SE of MAE ≈ σ/√n ≈ 0.07°F
- SE of lift = (raw-prod)/raw ≈ √2 × 0.07 / 5 ≈ **~2%**
- So ±3% was ~1.5σ (over-conservative); ±2% ≈ 1σ (real drift surfaces earlier at cost of more color churn on noisy fields)

Files touched:
- `analysis/scoreboard_v2.py:94-95` — constants 3.0 → 2.0, -3.0 → -2.0
- `corrections_debug.html` — five spots: two `_cls` fns (lines 4255-4260, 4424-4429), inline lift cls (line 2519), WFL bucket splitter (lines 4310-4311), plus updated comment (line 4292-4293)

## Product state
- **7D Total Lift median: +0.0% → +0.2%** (crossed break-even during session; still yellow under new ±2% band).
- **7D Pipeline Lift median: +2.3% (green), 24H +1.6% (green)**. 0 losing on pipeline.
- **7D Selector Skill median: +2.3% (green)**. 24H -12.6% (red, noise).
- **Total NBM selector picks: 10** (from yesterday's v0.6.500).
- Router-scope ship-gate NBM lift +53.4% n=72,158 (today's refit).

## Deferred to future sessions
- 08-28 scheduled review of NBM skip-table proposals (per calendar; wait for sustained-7d post-backstamp).
- L4_FIELDS drop cc — gate at 6/7 today, clears 08-28.
- sr.l5_nbm HOT will decay out of sentry window in ~1 day (auto-clears).
- chp_nbm HOT to watch; currently shadow-only impact.

## Housekeeping
Committed 6 files for v0.6.510 (analysis/scoreboard_v2.py, corrections_debug.html, docs/CHANGELOG.md, index.html, sw.js, version.json). 928c523 → 6724e4a. ~40 curated JSON + cache files from morning digest runs left uncommitted (routine daily drift; not part of the ship).

## Rules reinforced this session
- Don't guess — verify. Every HOT sentry looked scary until the actual mechanism check made it non-actionable. Sub-15-minute grep-and-read per signal.
- 24H median on a paired-lift metric is inherently noisy; 7D is the ship-relevant window.
- Threshold choices should match the empirical noise floor of the metric, not just match other thresholds by convention.
