---
name: 09-03-session
description: "2026-09-03 Thu session: 2 ships + 1 collector deploy. v0.6.543 NBM walkforward stale-DROP registry. v0.6.546 L1 selector recency-override — 10 cells flip HRRR→NBM, all traced to v0.6.540 09-02 writeback fix unlocking honest NBM-side numbers that the 30d fit pool is still averaging in with pre-fix corrupted data. Debug-page Selector Skill was median -4.4%, hit rate 54.1%, value captured -28.4% at ship. Also: dp -91.6% traced to v0.6.540 warmup with Fri 09-05 6-11h re-check trigger; l4_nbm cc DROP proposal verified as REAL (not the no-op the initial hypothesis assumed) deferred to 09-09 curation."
metadata: 
  node_type: memory
  type: project
  originSessionId: 46a33a93-0070-4414-a452-3ba08bf441da
  modified: 2026-09-04T00:31:46.329Z
---

# 2026-09-03 Thu session

Triage-focused day that turned into a real ship afternoon. Digest 180/180 pass. 2 ships, 1 collector deploy.

## Ships

### v0.6.546 — L1 selector recency override (afternoon ship)

`analysis/l1_selector_fit.py` — recency override layer added on top of the 30d fit. Cell flips iff last 7d has paired n ≥ 200 AND lift magnitude ≥ 5% in the OPPOSITE direction from the 30d pick. Same threshold-gate vocabulary as the base pool. Runtime `l1_selector.pick_source()` reads only the final `source` key — no runtime change, new fields (`source_30d`, `source_recent`, `override_reason`, `recent_*_prod_mae`, `recent_lift_pct`, `recent_n`) are pure metadata.

**Why:** Debug page Selector Skill was median **-4.4%**, hit rate **54.1%**, value captured **-28.4% median / -16.3% mean**. Read-only 7d refit vs live 30d curated found **10 flips, all HRRR→NBM, zero the other direction** — a systematic signal, not noise. Almost certainly caused by v0.6.540 09-02 writeback fix unlocking honest NBM-side numbers for sr/dp/t; the 30d pool is still averaging in pre-fix corrupted data.

**10 recency overrides applied on refit — all HRRR→NBM:**
- sr all 4 bands (rec +11% to +16%; 30d still shows HRRR winning by 100-160% from pre-fix stale data)
- h 6-11 (+19%), h 12-23 (+26%)
- dp 0-5 (+12%)
- t 24-47 (+25%)
- wd 0-5 (+14%)
- ws 24-47 preserved as NBM after 30d lift dipped below the 3% base threshold — recent +17.5% held the pin. **Override also acts as a stability floor when 30d bounces around pool threshold.**

Ship gate (router-scope t/ws/wd @ leads ≥6h): **+48.4% NBM lift on n=72,475**, well above 90% floor (was +50.4% pre-override, near-identical).

Deployed 00:18 UTC (rev 00549-qug). First run on new revision at 00:27 UTC verified cold-start (48 MiB start_rss vs prior 1075 MiB). Watch: [[project_selector_recency_override_watch]].

### v0.6.543 — NBM walkforward stale-DROP registry (morning ship)

`analysis/runlog/build_executive_summary.py` — new `KNOWN_DISABLED_NBM_DROPS` registry, same class as `KNOWN_LIVE_PIPELINES`, one layer down. The NBM walkforward validator compares proposed field sets against `L*_NBM_FIELDS` constants but has no knowledge of module `ENABLED=False` state, so it proposes DROP daily for layers already effectively off.

Two stale echoes suppressed:
- `(l5_nbm, sr)` — killed v0.6.471 2026-08-25 (sentry+walkforward agreed layer is net loss)
- `(l6_nbm, t)` — ENABLED=False scaffold pending NBM L2 double-count investigation

Suppressed drops still appear as transparent `·` lines in the digest with reason (visible not hidden). Real DROP signals (`l4_nbm cc`, `wdp_nbm wd`) and all ADD signals (`l3_nbm ADD dp,sr,t,wd,ws`) pass through unchanged. Same pattern as v0.6.538.

## Scoreboard read at start of session — scores were bad

24h value-add mean **-7.53%**, 7d **+3.51%**, 4 red / 3 amber / 2 green. Per-field worst:

| field | HRRR | NBM | l1sel | prod | total |
|---|---|---|---|---|---|
| dp | 2.45 | 1.19 | 2.45 | 2.28 | **-91.6%** |
| ws | 2.13 | 1.61 | 2.13 | 2.10 | -30.9% |
| h | 6.95 | 5.21 | 5.88 | 6.72 | -28.9% |
| wd | 34.4 | 29.4 | 38.1 | 37.2 | -26.7% |
| wg | 6.35 | 3.21 | 4.23 | 3.79 | -18.0% |

L5 rolling ladder over last 7 days: **+2.8 → +2.1 → +1.8 → +0.8 → -0.2 → -0.7 → -3.0**. Monotonic slide, not noise.

**Root cause identified by afternoon session: the selector was routing to HRRR on cells where NBM had quietly become the better cascade post-v0.6.540. v0.6.546 fixes this at the routing layer.**

## dp -91.6% investigation → warmup, not bug (with watch trigger)

Traced to v0.6.540 warmup artifact. Fix landed 09-02 16:17 UTC = ~19h before digest ran; pair log keys by forecast issue time, so long-lead bands (12-47h) are almost entirely pre-fix HRRR-derived pairs still closing out.

Per-band evidence (24h window):
- 0-5h (mostly post-fix): prod 1.15 vs NBM raw 1.54 = **+25.4%** — Ldp corrections beating NBM raw, fix working correctly
- 6-11h (mixed pre/post): prod 1.58 vs NBM raw 1.34 = **-17.6%** on n=105 thin
- 12-23h (mostly pre-fix): prod 2.56 vs NBM 1.31 = -95.8%
- 24-47h (100% pre-fix): prod 2.53 vs NBM 1.02 = -148.7%

**Prediction:** in 48h once all long-lead pairs in the window were issued post-fix, dp scoreboard should collapse from -91.6% to somewhere between flat and modestly positive vs NBM. ~15-20 point swing in overall scoreboard mean from dp alone. **v0.6.546 flips dp 0-5 to NBM route** — will accelerate the recovery on that band.

**Fri 09-05 re-check trigger:** if 6-11h band holds at ≈-15% post-full-warmup, L2_nbm Kalman+decay is net-harmful for dp at short-mid lead = real bug. See [[project_dp_v0540_warmup_watch]].

## Investigation no-ship — l4_nbm cc DROP is REAL

Initially hypothesized this was 15-min cleanup: "Ccd overwrites hourly.cloud_cover downstream → l4_nbm cc is no-op." **Wrong.** Ccd only overwrites the HRRR-side `hourly.cloud_cover` value. l4_nbm cc computes on the separate NBM cascade (`cc_l4_nbm = cc_l3_nbm - correction(cc, hod)`) inside forecast_snapshot. When the selector picks NBM for cc (which it does since v0.6.540 — digest sel_n +16.3%), users see NBM cascade values, not the Ccd-overwritten HRRR value.

Six hurting cells (~n=3,700 total, lifts -4.5% to -14.1%) reach production:
- pre_frontal 0-5h -6.2% n=365
- pre_frontal 6-11h -4.5% n=343
- se_flow 12-23h -12.9% n=846
- ne_flow 24-47h -14.1% n=525
- se_flow 24-47h -4.6% n=1,330
- sea_breeze 24-47h -10.3% n=284

The debug-page-elsewhere comment "cc excluded from l3_nbm ADD list because Ccd overwrite makes cc L3_NBM no-op" is itself stale reasoning that only held pre-v0.6.540.

Deferred to 09-09 skip-table curation session — full 30-60 min slot to design DROP entirely vs selective skip-table cells vs Ccd/NBM interaction rethink.

## Clock-watches advancing

- cc blend Stage 1: day 2/7 but **CHURN** (pre_frontal dropped from SHIP set → gate reset risk; still 3 SHIP regimes frontal/ne_flow/sea_breeze)
- L4 add cc: 2/7 → 3/7 if it holds
- h/wg/dp residual persistence walkers: 5/7 → 6/7 (earliest wire ~09-06)
- L1 by-regime walker: suppressed until 09-07
- sr Stage 1 stability watch: day 3 → 4
- t/τ watch: day 6 → 7
- NBM skip-table curation: 09-09 (6 days)

## Lessons

- **Almost missed a real selector-level ship by waiting.** Told user "wait for individual gates to mature" all week. When user pushed with "is waiting even safer?" the honest answer was no — value captured -28% is a running tax, halves-agree 80% is not a noisy-week fingerprint. Selector-level diagnosis was actionable independent of any single gate. Same failure mode as [[feedback_broader_than_gate_cleared]] applied one layer up: gate-cleared discipline shouldn't block cross-cutting infra fixes.
- **ELI5 initially wrong on load-bearing point.** Told user the fix was "add a per-cell cheat sheet" — but that already existed. Recognized in time to correct before shipping and pivoted to the real fix (recency override on top of the existing cheat sheet). [[feedback_check_own_arithmetic]] applied to architecture reads.
- Almost missed real ship candidates by narrow "no gate cleared = noop" framing at session start. User pushed twice ("there must be something for today" + "what else?") to break through. Pattern is [[feedback_broader_than_gate_cleared]] — enumerate categories before declaring noop: infra queued, unshipped signals, uncommitted work, investigations, refactors, debug page, memory.
- The "quick 15-min cleanup" cc l4_nbm ship framing was wrong. Ran through the ordering + selector paths in ~10 min and found it was actually a real production signal, not dead code. Small time cost, big correctness value — pattern is [[feedback_verify_writers_for_read_paths]] applied to cascade interactions.

Related: [[project_selector_recency_override_watch]], [[project_dp_v0540_warmup_watch]], [[project_09_02_session]], [[cc-blend-formula-stage1]].
