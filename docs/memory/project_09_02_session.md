---
name: 09-02-session
description: "2026-09-02 Wed session: 6 ships + 2 collector deploys. Ships include a real prod fire fix (NameError shadowed datetime in collector) and a major infrastructure bug fix (L1 selector scope-mismatch — 4 of 9 selector-table fields were being silently dropped by the runtime writeback loop). Also cc blend formula Stage 1 built, c1-axis triage cleared 3 stale PROMOTEs, leaky Stage 1a script skipped."
metadata: 
  node_type: memory
  type: project
  originSessionId: e218572d-d5db-4370-b7b7-f278ad0d6f2e
  modified: 2026-09-02T17:46:54.050Z
---

# 2026-09-02 Wed session

Substantial day. 6 ships, 2 collector deploys. Digest 180/180 pass.

## Ships

### v0.6.536 — `h_lc_ema_stage1_baseline.py` renamed `.skip.py`

Digest surfaced `info→promote` LOOKBACK verdict; investigation traced to the same obs-time-keying leakage class the 08-17 [[project_lc_ema_kalman_fallback]] CLOSED-MISS memo retracted. Script batches by `obs_time` and applies a shift built from prior obs_times up to `ot`, but the forecast was issued at `ot - lead_h` — obs from `[ot - lead_h, ot]` are peek-ahead. Docstring of `h_lc_ema_stage0.py` corrected (its "honest run-time-keyed" claim was never true). L4 add cc streak triaged: genuinely day 1 today (yesterday's session log's "expected 2/7 today" was wrong; `digest_history.jsonl` shows the divergence only opened 09-02).

### v0.6.537 — cc blend formula Stage 1 halves-verify built

New `analysis/h_cc_blend_formula_stage1.py` closes pipeline gap between Stage 0 pooled signal and per-cell walker `h_cc_combine_walker` (regime × band × day 7-day unanimous gate, HOLD 0/27). Regime-granularity curated table + 7-day set-stability gate history. Day 1/7 reads 4 SHIP regimes (frontal +5.20%, ne_flow +7.88%, pre_frontal +5.65%, sea_breeze +5.13%), all prefer `random` over live `max`. se_flow demoted SKIP-ccd; sw/nw/calm demoted SKIP-mag (halves A negative — recent-anomaly Stage 0's "both positive" bar missed). Earliest wire ~09-09. See [[cc-blend-formula-stage1]].

### v0.6.538 — c1-axis triage: 3 stale PROMOTEs → KNOWN_LIVE

`h_hsf_orthogonality`, `h_cross_run_spread_c1_stage1` + `stage2` all reading PROMOTE for 10+ consecutive days but the targets have been LIVE (C1e since v0.6.316 2026-07-01; cross_run_spread since v0.6.401g 2026-08-12). Added registry entries to `analysis/runlog/build_executive_summary.py::KNOWN_LIVE_PIPELINES`. Also verified `h_cl_h_predictor_stage1.py` is honest (run-time-keyed, not obs-time — memory flag on [[project_lc_ema_kalman_fallback]] cleared).

**Genuine unwired c1 promotes flagged for future:** `forecast_magnitude` (wg/dp, stable 10d — real ship candidate, would be a new C1 axis, 4-6 hr build); `recent_err_streak` (t/wg/4-12, churning day-over-day — not ready).

### v0.6.539 🔥 collector NameError prod fix + deploy

Cloud logs surfaced `NameError: cannot access free variable 'datetime'` at `collector.py:125`. Root cause: local `from datetime import datetime, timedelta, timezone` INSIDE `build_weather_data()` at line 300 shadowed the module-level import at line 12 for the entire function scope. Python compile-time analysis marks name as function-local once it sees any local assignment, so the earlier use at line 125 (Pirate Weather HRRR fallback list comprehension) raised NameError. Trigger: Open-Meteo 429 rate-limits → Pirate fallback path → crash → data didn't write → next tick same crash. Fix: deleted redundant local import. Deploy verified two clean ticks (14:47, 14:57 UTC).

### v0.6.540 — 🔥 L1 SELECTOR SCOPE-MISMATCH BUG + deploy

User pushed on "why is selector so bad while pipeline is good?" — investigation followed.

**The bug:** selector table has entries for **9 fields** (t/dp/h/ws/wg/wd/cc/ch/sr); runtime writeback loop in `forecast_snapshot.py:912` iterated **5** (`_L3_NBM_FIELDS + wd`). Picks for t/dp/ws/sr were silently dropped — table said route-to-NBM, runtime kept shipping HRRR-derived, attribution `{f}_selector_source` never stamped. dp's `-88%` scoreboard line was the tell (read as "picked NBM and it went wrong," actual cause was "picked NBM, silently discarded, shipped HRRR").

**Latent risk (now closed):** by-regime walker (v0.6.534) is built to detect NBM wins for t/ws/sr — those picks would have silently dropped too.

**Fix 1:** `forecast_snapshot.py` loop expanded to all 9 fields; guard changed from "l3_nbm exists" to "raw_nbm exists"; NBM fallback chain extended to `l2_nbm > raw_nbm` tail.

**Fix 2:** `l1_selector_fit.py _nbm_prod_error` walker extended from `l6/l5/l4/l3` to `chp/l6/l5/l4/l3/l2/raw` — fields with only NBM L2 (v0.6.499) get honest fit comparison.

**Refit result:** ws 24-47 flipped HRRR → NBM (+3.0% on n=12,900); dp/wg/wd/cc NBM picks now honored at runtime; t/sr/ch/h correctly stay HRRR. Ship gate +51.4% on n=70,558.

Deploy verified 16:17 UTC — snapshot log confirms `dp_applied = l2_nbm`, `dp_selector_source = nbm` stamped for the first time.

### v0.6.541 — debug page sweep

09-02 (Wed) narrative added; 09-01 → 1 day ago, 08-31 → 2 days ago; 08-30 detail entry rolled to "and earlier" pointer.

## Discussion sidebars

- Confirmed the [[feedback_baseline_is_user_default]] framing at work: pipeline `+36% wg` / `+68% ch` lift-vs-HRRR looks big because the stack was fit on HRRR error; NBM's national MOS blend is a much harder baseline on fields where HRRR's coastal physics is weak (t/dp/sr).
- Reset user's "6-9 month" pessimism about selector improvement — actual timeline ~2 months for mechanical improvements (walker + writeback + NBM cascade fill-in) to land.
- Corrected earlier framing that had confused vs-HRRR (pipeline diagnostic) with vs-best-public (ship signal). Real red-count is 5-of-9 not 6-of-14.
- Confirmed collector memory leak still active: ~30-70 MiB per tick, instances OOM at ~1 GiB → recycled. Not a stability threat; [[project_collector_memory_leak_hunt]] on watches list.

## Watch state at session end

- dp scoreboard `-88%` REGRESS should collapse toward flat over next 24h as prod dp shifts HRRR-derived → NBM L2 (~1.66°F)
- L4 add cc gate: day 1/7 → 2/7 tomorrow (if still divergent)
- cc blend Stage 1 gate: day 1/7 → 2/7 tomorrow (if 4 SHIP regimes hold)
- h/wg/dp residual persistence walkers: day 4/7 → 5/7
- L1 by-regime walker: still suppressed until 09-07
- sr Stage 1 stability watch: day 2 → 3
- t/τ watch: day 5 → 6
- Memory index compacted (22.5KB → target ≤17KB) in same session
