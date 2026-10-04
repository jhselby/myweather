---
name: project-06-18-session
description: "2026-06-18 session — Gemini key rotation, briefing sanity-check bug fix (v0.6.129), and refreshed state of R2/R6/L5 + L3/L4 whitelist. Supersedes the R5 plan and parts of the 06-08-to-06-22 plan."
metadata: 
  node_type: memory
  type: project
  originSessionId: 33bfbee9-73c0-495c-8376-709eae46444d
---

## Shipped today

- **v0.6.129** — `_validate_headline` in `weather_collector/fetchers/briefing_ai.py` now uses word-boundary matching (`\bword\b`) instead of substring `in`. Substring match was rejecting valid headlines whose sub contained "clearing" (matches "clear") on overcast days, then falling through to a 4-hour-old cached headline. Caught when Joe noticed the briefing reverting to an older Groq line. Both Gemini 09:37 and Groq 12:17 were false-rejected before the fix.
- **Gemini API key rotated** — old `...X41w` key was on "Weather Data" project, Tier 1 Prepay (no credits) → returning 429 "prepayment credits depleted." Joe switched GC `gemini-api-key` secret to the `...A-Qw` key on the new free-tier project "WymanCoveWeather20260618" (gen-lang-client-0122671252). Confirmed working post-rotation. The 503s seen after the switch were genuine `gemini-2.5-flash-lite` server overload — transient, unrelated to the key.

## Decision: leave 503 handling as-is

In `briefing_ai.py:588-638`, 5xx already gets one 5s in-tick retry, then falls through to the normal 30-min throttle. 429 sets `last_429_at` and triggers a 4h cooldown. So 429 and 503 are NOT treated the same — 429 = 4h backoff, 503 = next normal tick. Joe considered shortening 503 backoff to next-tick (10m) but declined; current behavior is fine pending more 503 incidents.

## Hypothesis pipeline state at 06-18

- **R5 (cove gradient)** — **RETIRED.** v0.6.124 "autowire R6 + strip R5 from Fitter" did the cleanup. Held-out MAE audit (`analysis/r5_audit.py`) re-confirmed today: R5 makes temp MAE 22-23% worse vs baseline across all regimes/bands. Audit verdict: "L2's station weighting already captures the waterfront signal." The L5 candidate stamp for R5 can be retired from anywhere it still appears. **Do not revive without strong new evidence.**
- **R6 (regime-transition penalty)** — audit is auto-wired and live (v0.6.124). **Shadow tuner returned its first SHIP verdict on 2026-06-18T03:07** (25/56 buckets flagged, worst pp 24-47h at +514%, n=1,144,719). This is **one read, not a confirmed pattern** — the prior 4 fitter cycles had r6=None because the audit had just started populating. Need at least one more SHIP cycle before promoting to C1 implementation (per [[feedback-hypothesis-promotion-pipeline]] and the two-runs-must-agree discipline).
- **R2 (state-stratified MAE)** — re-run today on 879k pairs. Top spreads unchanged: Solar × wind dir (86), Solar × wind speed (62), Solar × cloud cover (50), Cloud cover × flow regime (17). Temperature spread small (<0.7°F) across every dimension — temp is well-corrected, no temp-side R2 work left. Verdict line: "Solar rad. stratified by flow regime (obs) shows 139.47-unit spread — worth building a regime-aware correction layer" — that's the L5 thesis, still standing.
- **L5 (solar regime correction)** — `solar_correction.py:43 ENABLED = False`, still in shadow. Shadow tuner's L5 verdict on 06-18T03:07 is **HOLD** (mae_with_layer 173.57 > baseline 167.66, -3.53% improvement, 3 of 8 regimes winning). This is a flip from the 06-15 ship-candidate state (where L5 was at +31.6% MAE drop in early reads). Decision still gated on 06-22.
- **L6** — doesn't exist yet. Would be the correction layer matching R6's audit. Pending second R6 SHIP confirmation.

## Walk-forward L3/L4 re-run (06-18 result)

- `L3_ENABLED = {'ws', 'wg', 'ch', 'cm'}` — **unchanged from 06-08**. 4-of-4 stable across 10 days, 143k held-out rows. L3 is ship-ready, awaiting the 06-22 third read per the discipline.
- `L4_ENABLED = {'ch'}` — **shrank from 06-08** when it was `{'ws', 'wg', 'ch'}`. Wind L4 now ties exactly with L3-alone (ws 1.887/1.887, wg 3.121/3.121) — no longer earns its keep at the 2% threshold. Only `ch` (cloud-high) keeps L4. Confirm/disconfirm on the 06-22 run.

## Side bug caught (not fixed)

`analysis/r5_audit.py` (and likely any other `_cache.py`-using script) has a **concurrent cache write/read race**. First run reported "0 matched pairs" because the script started iterating the partial cached pair log while the download was still streaming. Fresh run with the cache fully populated → 39,841 matches. Fix is atomic write in `analysis/_cache.py` (download to `.tmp`, then `os.replace`), or a "wait for full cache" gate. Worth doing before the next batch run.

## Stale memory cleanup

These should be considered superseded by this note:
- [[project-r5-two-step-plan]] — R5 retired, the two-step plan is moot
- [[project-r4-r5-hypotheses]] — R5 retired; R4 status not re-verified today, leave as-is until reviewed
- [[project-06-08-to-06-22-plan]] — calendar is partially executed; R5 portions are dead, L3/L4 06-22 third-read still scheduled
- [[project-06-15-session]] — R5 candidate language is no longer accurate

Related: [[project-correction-stack]], [[feedback-hypothesis-promotion-pipeline]], [[project-walkforward-l3l4-validator]], [[feedback-whitelist-promotion-gate]], [[project-gemini-quota-real]].
