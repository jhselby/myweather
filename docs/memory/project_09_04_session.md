---
name: 09-04-session
description: "2026-09-04 Fri session: 3 ships + 1 collector deploy. v0.6.548 nbm_regression_sentry marginal-help refactor (kills raw-weather false HOTs on wd/wg l3_nbm, surfaces real WATCH on h.l3_nbm). v0.6.549 L3_NBM adds sr — first NBM cascade extension since 08-26, walkforward +12.8% aggregate all bands positive. v0.6.550 debug page sweep. Also: prep memo [[l4-nbm-cc-drop-prep]] written for 09-09 (recommend DROP l4_nbm cc entirely — best skip-table only +60bp over DROP baseline). dp warmup partly healed (scoreboard -91.6% → +10.6%) but NBM raw dp jumped 1.9 → 3.5 in the 27h post-fix — Fri 09-05 real read pending backstamp."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1f984b98-d729-43cb-b74b-2c8735715f86
  modified: 2026-09-04T17:05:28.578Z
---

# 2026-09-04 Fri session

3 ships + 1 collector deploy. Digest 180/180 pass. Session opened as "no gate-cleared items today, mostly wait-and-watch" but broke through into two actionable ships (sentry design bug + walkforward-proposed L3_NBM sr add) after enumerating categories per [[feedback_broader_than_gate_cleared]] — same lesson yesterday's session captured.

## Ships

### v0.6.548 — NBM sentry marginal-help refactor (analysis-only)

`analysis/nbm_regression_sentry.py` — verdict now uses **marginal layer effect**, not absolute cascade MAE.

**Why:** Morning digest surfaced two false-positive HOTs (wd.l3_nbm ΔMAE +41%, wg.l3_nbm ΔMAE +58%) driven by raw NBM inflating in the fresh window (wd raw +34%, wg raw +72%). The old sentry couldn't distinguish "layer regressed" from "raw got harder." On the wg case the layer was actually helping MORE fresh (+16.4% vs +9.1%).

**How:** New `LAYER_INPUT` map identifies each layer's cascade input (l3_nbm→l2_nbm, l4_nbm→l3_nbm, chp_nbm→l4_nbm, wdp_nbm→l3_nbm, etc.). For paired rows carrying both layer and input errors we compute `layer_help_pct = (input_MAE − layer_MAE) / input_MAE` per window and set the verdict on `Δhelp_pp = help_sustained − help_fresh`. HOT thresholds unchanged in name (≥15pp / ≥8pp) but now measure marginal degradation. HOT also fires if a layer flipped from net-helping to net-hurting. Absolute ΔMAE% still reported for context; if a layer lacks input-pair data the verdict falls back to the old absolute rule with `[absolute fallback]` note.

**Re-run cleared both HOT flags** (wd/wg both CLEAN under marginal metric) and **surfaced one real WATCH: h.l3_nbm help +20.5% → +10.4% (Δ +10.1pp)** that was buried by the old absolute metric (h raw got easier, absolute ΔMAE −24.6% masked that the layer's own contribution halved).

Also updated `analysis/runlog/build_executive_summary.py` to render the new marginal fields.

### v0.6.549 — L3_NBM adds sr (first NBM cascade extension since 2026-08-26)

`weather_collector/processors/l3_nbm.py` — `L3_NBM_FIELDS` gains `"sr"`.

**Why:** Walkforward has been proposing `l3_nbm: ADD sr` on n=2,367 paired rows with **+12.8% aggregate lift** and all four lead bands positive (0-5h +18.6%, 6-11h +19.4%, 12-23h +12.6%, 24-47h +8.2%). No hurting cells surfaced in skip-proposals for sr. Gives sr its first NBM-side hour-of-day correction — previously sr's NBM cascade dead-ended at raw + L2_nbm (L5_nbm sr killed v0.6.471 08-25).

**Curated coefficients already emit** from `analysis/l3_nbm_fit.py` in `l3_nbm_curated.json`: 48 lead-hour bins, n_samples 574-626 for leads 0-33h, thinning to 84-368 at leads 34-47h. Corrections are large diurnal-shaped (subtract 37-52 W/m² for most short-mid lead bins, near-zero at long lead where NBM raw is already reasonable).

**Selector interaction:** L1 selector already routes all four sr bands to NBM (per 09-03 v0.6.546 recency override — all four sr bands overridden HRRR→NBM on 7d evidence). Adding this L3 correction on top will improve NBM's prod-side MAE further, likely widening NBM's lift and solidifying hit rate on the four flipped cells.

**Deploy verified:** rev `00550-sas` active 15:30 UTC; cold-start at 15:37 UTC (start_rss 50 MiB, clean signature); 8+ runs since, no `l3_nbm` warnings in logs.

### v0.6.550 — debug page sweep (session-end)

`corrections_debug.html`:
- New 09-04 (Fri) Recent Activity entry as "today" with the full session narrative
- Day-labels shifted (09-03 → 1 day ago, 09-02 → 2, 09-01 → 3, 08-31 → 4)
- L3_NBM scope refs updated in 2 operational-state paragraphs
- 09-04 calendar item closed (NBM POP first 7d landed; digest's `pp_brier_reliability` CLEAN weighted_bias -1.44pp = no Stage 0 candidate; `chp_nbm` 14d re-eval healthy)
- Removed stale "cc.l4_nbm HOT flag today" reference — under new marginal-help sentry it reads CLEAN

## Prep memo written for 09-09 curation

New memory: [[l4-nbm-cc-drop-prep]]. 30d per-cell analysis (n=27,313, 30 regime×band cells) shows l4_nbm cc pooled lift is only **+0.79%** over L3_NBM. Best possible skip-table gets +1.38% (only 60 bp above DROP baseline). Cells flip verdict as window slides (se_flow 24-47h was -4.8% recently, +1.2% on 30d) = high-maintenance skip-table for marginal gain.

**Recommendation: DROP l4_nbm cc entirely.** Scope is clean: cl/cm are NBM-nonexistent (NBM doesn't emit them); Ccd applies HRRR-side only; l4_nbm ch stays (sentry marginal help +13.7% → +17.1%, actually improved fresh). Walkforward already proposes DROP; this analysis backs it.

## Investigations completed

### h.l3_nbm WATCH cell breakdown (new sentry surface)

Real degraders (n_fresh ≥ 100):
- **ne_flow 24-47h** help +43.6% → **-18.8%** (Δ +62pp, n_fresh=202) — cleanest signal
- pre_frontal 0-5h help −0.7% → −101.5% (Δ +100pp, n_fresh=79, borderline thin)

Real improvers (n_fresh ≥ 100):
- **se_flow 24-47h** −22.7% → **+37.0%** (Δ −60pp, n_fresh=703) — massive helper
- se_flow 12-23h +4.6% → +20.9% (Δ −16pp)
- pre_frontal 24-47h +5.1% → +26.0% (Δ −21pp)

**Verdict: fresh-window weather-mix artifact, not a systemic h.l3_nbm regression.** Big real degrader (ne_flow 24-47) roughly cancelled by big real improver (se_flow 24-47). Pool marginal halved because regime × band n-weights shifted, not because layer broke. Re-check next week — if ne_flow 24-47 keeps hurting it becomes a skip-cell candidate.

### t/h selector routing NOT a bug (per scoreboard reframe)

Initial read of per_field_scoring said "corr -77.3% on h means correction stack is hurting after selector picks NBM." User pushback via debug-page scoreboard image showed **NBM Pipeline Skill h +17.7%, t +4.7%** — NBM's own raw→prod improvement is healthy.

Investigation showed:
- **t 30d and 7d paired fits BOTH show HRRR-prod winning by 27-41% on 0-5/6-11/12-23** (HRRR t Kalman/L2 stack is legitimately better at short lead). Override rule requires opposite-sign 7d — same-sign in both windows = no flip. Working correctly.
- **h selector IS picking correctly** (l1sel 4.22 vs hrrr 7.76). The scoreboard's Value Captured -96% reflects pair-log rows stamped BEFORE the v0.6.546 override — where we were routing HRRR at h 6-11 and h 12-23 (2.1× worse than NBM there). Should heal to positive Value Captured as pair log rotates over ~24h.

Lesson: [[feedback_check_own_arithmetic]] applied to scoreboard column semantics. "NBM Pipeline Skill" is NBM raw→prod self-improvement, not HRRR-vs-NBM. Doesn't argue for flipping.

### dp warmup early peek — HRRR healing, NBM question open

Post-fix (last 27-45h) HRRR-prod MAE: 0.86 at 0-5h, 1.74 at 6-11h, 1.19 at 12-23h, 2.61 at 24-47h on n=118-234 per band (fresh GCS pair log pulled 12:53 UTC). HRRR dp is genuinely good on recent weather.

Scoreboard read this morning: dp **-91.6% → +10.6%** — warmup healing well as pair log rotates.

**Open question pending 09-05 backstamp:** NBM raw dp appeared to jump 1.9 → 3.5 in the 27h post-fix window on the earlier peek. If that persists in tomorrow's fuller backstamp:
- Fri 09-05 trigger for [[project_dp_v0540_warmup_watch]] fires with a bigger delta than anticipated
- v0.6.546 override of dp 0-5 (HRRR→NBM) may have been premature and should flip BACK on next recency-override refit

Not shipping anything based on this today. Fresh backstamp tomorrow gives the honest read.

### NBM walkforward ADD backlog surveyed

All 5 candidates (dp, sr, t, wd, ws) show EARN. Only sr was clean enough to ship today:
- **sr** (shipped) — +12.8%, all bands positive, no skip cells
- **t** — +5.2%, all positive, 1 skip cell (pre_frontal 12-23h -4.3%)
- wd — +4.4%, 3 skip cells
- ws — +4.5% aggregate but 0-5h/6-11h ≤0, needs partial ship (long-lead only)
- **dp** — +35.6% but n=827 thin, defer

Any of the remaining 4 could be next candidates as their n accumulates.

## Scoreboard read

24h value-add mean **-6.0%** (up +1.5pp from yesterday's -7.53%), 7d **+4.14%** (steady).

Per-field 24h recoveries:
- dp: **-91.6% → +10.6%** (v0.6.540 warmup rotating in)
- ws: **-30.9% → +33.8%**
- wg: **-18.0% → +13.1%**

Per-field 24h regressions:
- h: -28.9% → **-46.6%** (not a routing bug per investigation — pair log lag on selector picks)
- t: fine → **-62.6%** (also not a routing bug — HRRR t Kalman legitimately wins at short lead)
- sr: -62.1% (l1sel = hrrr in scoreboard = pair log lag; override only 10h old at digest time)

Expect meaningful improvement in tomorrow's digest as override picks accumulate in the pair log.

## Lessons

- **"Just wait and watch" would have missed both today's ships.** Session opened with a light SHIP-eligible list (only walkforward L4 cc gated 3/7). Only by enumerating categories per [[feedback_broader_than_gate_cleared]] did the sentry design bug and the walkforward-proposed sr ADD both surface. Same class of lesson as yesterday's "capitulated to wait-for-gates all week when cross-cutting selector-level ship was actionable independently."
- **Trust the user's scoreboard read.** Initial per_field_scoring read said "h correction stack is hurting." User pushback with scoreboard column showed NBM Pipeline Skill was +17.7% — reframed the whole investigation. [[feedback_check_own_arithmetic]] applied to column semantics.
- **Marginal is the honest layer-regression metric.** The old sentry conflated layer regressions with raw-weather difficulty shifts, silently masking real signals (h.l3_nbm marginal halving) while firing on noise (wd/wg raw drift). Same class of design bug as [[feedback_baseline_is_user_default]] applied to layer-effect measurement.

## Clock-watches advancing

- h_cc_blend Stage 1: day 3/7 (still CHURN from yesterday's pre_frontal drop; no new churn today; gate clears ~09-08 if stable)
- L4 add cc: 3/7
- h/wg/dp residual persistence walkers: 6/7 (earliest wire ~09-06)
- L1 by-regime walker: suppressed until 09-07
- sr Stage 1 stability watch: day 4
- t/τ watch: day 7
- NBM skip-table curation: 09-09 (5 days) — **now backed by [[l4-nbm-cc-drop-prep]]**

Related: [[project_selector_recency_override_watch]] · [[project_dp_v0540_warmup_watch]] · [[l4-nbm-cc-drop-prep]] · [[project_09_03_session]] · [[cc-blend-formula-stage1]].
