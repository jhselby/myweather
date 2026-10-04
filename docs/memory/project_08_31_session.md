---
name: project-08-31-session
description: 2026-08-31 Mon session — 7 ships + 2 collector deploys. Residual-persistence stack fully refactored + h Stage 3 pre-staged + promotion walker built. Session ends set up for audit.
metadata: 
  node_type: memory
  type: project
  originSessionId: a29ce1bf-0957-49ab-aaf1-66e92fba77a9
  modified: 2026-08-31T16:43:15.292Z
---

# 2026-08-31 Mon session

## Evening addendum — audit sweep (~1.5h, v0.6.533 shipped)

Joe requested useful work on remaining weekly-budget time. Ended with 4 findings + 1 ship + 1 memo supersession:

1. **[[project_nws_dp_promote_08_31]]** — 13-day-overdue NWS-gridpoint benchmark fired. **dp PROMOTES strongly** (Δ_prod=+44.6%, halves +35/+52 both stable, n=12,016). Ship shape refined via regime × lead-band drill: use NWS-dp L1 override at 6h+ leads for regimes {w, sw, nw, n, s}; skip {e, se, calm, ne} (halves-flippy); skip 0-5h everywhere (L2 wins short-lead). Architectural conflict with [[project_dp_is_derived_no_dp_work]] is the exact "stated reason" carve-out. t/pp/ws/wd all KILL.

2. **[[project_sr_stage2_08_31_read]]** — sr sea_breeze Lsr shortwave Stage 2 re-run with 6+ weeks accumulated data. Pooled = HOLD (Δ -0.22%), but hours 17-18 concentrate clean narrow ship signal (+25.9% on 244 firing rows, halves 2/2 both cells). Cause B strongly confirmed for sea_breeze (matched-bin +86, was +83 on 07-11). pre_frontal shifted toward Cause A (matched +16, big-miss +47) — permanent-defer signal.

3. **[[project_t_6_11h_tau_watch_08_31]]** — day-3 pre-read on the READ FIRST τ-suspect. L2 flipped from +5% helping to -7% hurting week-over-week, but absolute Δ ~0.075°F/day still within noise band. Authoritative 457K-row `decay_tau_tuning` still says τ=42 optimal. WATCH day 4.

Also confirmed: initial "regime null in NWS-dp pair rows" was a drill-code bug in my scratchpad (used wrong key path), not a data-quality issue in the pair log.

**LATE-EVENING SUPERSESSION:** debug page recon revealed L1 selector (`l1_selector.py`) already lives + is wired + was refit today at 10:15 UTC. Ships dp/wg/wd/cc to NBM at ≥6h. My "NWS-dp promote" was measuring against a selector-routed baseline; memo [[project_nws_dp_promote_08_31]] updated with strikethrough + real residual finding: **selector fits band-level only; regime × band cells where NBM wins under a pooled-HRRR band are masked** (ws has 8 halves-stable NBM cells hidden e.g. sw/24-47h +11% n=1142, w/24-47h +16% n=1080; t has 1 s/24-47h +21% n=817). Actionable: extend `analysis/l1_selector_fit.py` to per (field, regime, band).

**v0.6.533 SHIP (evening) — debug page audit sweep + changelog + version bump + `analysis/h_nws_gridpoint_benchmark.py` caveat header. No runtime code.** Deployed 4e43dec → eab9d06.

**Next-session decision-ready:** extend l1_selector_fit to per-regime granularity. NWS-gridpoint vs direct-NBM cross-check is a bounded side-audit.

## Ships (7) + deploys (2)

| Ver | Type | Summary |
|-----|------|---------|
| v0.6.527 | analysis | 6 residual-persistence wrapper FAILs — `sys.path.insert(0, SCRIPT_DIR)` added to all 6 (missing after v0.6.522/524 harness extraction) |
| v0.6.528 | analysis | Stage 1 harness picks halves-stable best, not raw-max then validate. h corrected PROMOTE→MARGINAL→PROMOTE (window=14d, +24.51%, halves +0.56/+4.10). dp/wg unaffected. Feedback: [[feedback_grid_select_halves_stable]] |
| v0.6.529 | analysis | Residual-persistence Stage 2 → Stage 3 promotion walker — shared `analysis/_residual_persistence_walker.py` + 3 thin wrappers. Gates on 7/7 consecutive days in {SHIP, MARGIN}. Day-1 today all three BUILDING. Earliest h clear ~09-06 |
| v0.6.530 | collector | h_residual_persistence.py Stage 3 processor pre-staged (wg template + FIELD=h + [0,100] both-ends RH clamp). Wired into collector.py ENABLED=False. **Collector deploy #1 today** |
| v0.6.531 | docs | Debug page sweep — 08-31 today entry + 08-29→2days + 08-28 to trim. 3 new post-ship watches. Candidate count 13→14 |
| v0.6.532 | collector | Stage 3 processor harness extracted (deferred v0.6.525 refactor — trigger fired when h became third clone today). Shared `_residual_persistence.py` + 3 thin wrappers. 690→445 lines (35% cut). Byte-hash `6b6c5293acc6126b` matched pre/post. **Collector deploy #2 today** |

**Why:** Full details in [[memory_index_08_31_read_first]] and MEMORY.md READ FIRST block.

**How to apply:** Fresh session should treat today's stack as freshly-refactored high-blast-radius live code — verify next digest confirms the 6 FAILs cleared and h Stage 1 verdict = STAGE 1 PROMOTE (not MARGINAL).

## Live-layer changes (audit targets)

1. **Stage 3 processor harness** (`weather_collector/processors/_residual_persistence.py`) — new shared module, 290 lines, running on every tick for wg + dp + h.
   - Pre-refactor semantic-preservation gate: 3 fields × 4 regimes byte-equivalent, sha256 `6b6c5293acc6126b`.
   - Post-deploy verify on ne_flow tick: all 3 stamps present, identical 9-key shape, fires 0 / skips 47 / clamped 0 (ne_flow has no SHIP/MARGIN cells for any of the 3 fields).
   - **Audit angle:** watch a few ticks across different regimes (nw_flow / sw_flow / se_flow). Fires+skips+clamped should always sum to 47. `per_lead_would_apply` values should match `l2_arr[i] + hour_of_day[hour(i)]` clamped to physical bounds.

2. **h_residual_persistence** processor now stamping telemetry on every tick (ENABLED=False shadow). Fires_by_band should track Stage 2's SHIP+MARGIN cells for the current regime.
   - **Audit angle:** compare live `fires_by_band` per regime to `h_residual_persistence_curated.json` cell verdicts. nw_flow should fire 47/47 (all 4 bands SHIP), calm should fire 0/47 (all 4 bands SKIP), etc.

3. **Stage 1 halves-preference** now the ship-gate in `analysis/_residual_persistence_stage1.py`. Wrote [[feedback_grid_select_halves_stable]] — future gates should follow the same pattern.
   - **Audit angle:** does h stay STAGE 1 PROMOTE tomorrow? Any override-line firing on wg/dp?

4. **Walker (`_residual_persistence_walker.py`)** now runs daily via digest. Emits per-field runtime table + history cache.
   - **Audit angle:** day 1/7 today. Tomorrow will be day 2/7. Verify history file grows by one entry per day, cell-series `S`/`M`/`K`/`T` string is consistent with Stage 2 verdicts.

## Open watches / tomorrow's signals

- **6 FAILs cleared** — tomorrow's digest should show all 6 residual-persistence wrapper scripts OK.
- **h Stage 1 = STAGE 1 PROMOTE at 14d** — halves-preference fix means the daily verdict should stay PROMOTE now.
- **h Stage 2 walker day 2/7** — verify walker accumulator working.
- **t/6-11h τ-suspect day 3/3** — TOP ALERT for 2 days now. Day 3 decides close-vs-investigate. Guidance: Δ 0.06°F, n=143/lead, `decay_tau_tuning` (n=457K) says t's τ=42 optimal — don't ship on evidence alone.
- **NBM sentries** (cc.l4_nbm, ch.chp_nbm, h.l3_nbm) — per [[feedback_nbm_regression_sentry_semantics]] sentry alone ≠ regression; cross-check walkforward EARN + product lift before treating as real.
- **NBM skip-proposals** — 36 cells identified 08-30. Hold until 09-09 (sustained-7d post-backstamp).

## Deferred / next-session candidates

- **Stage 3 processor harness extraction** — DONE today (v0.6.532). This was the deferred v0.6.525 refactor.
- Nothing else architectural deferred from today.
- Next natural work: watch tomorrow's digest, close τ-suspect (if day 3 confirms noise), continue accumulating walker days.

## Handy audit queries

Live weather_data (pass `max_age_hours=0` via MYWEATHER_REFRESH=1 for a fresh pull):
```python
import sys, json
sys.path.insert(0, '/Users/josephselby/Documents/myweather/analysis')
import os; os.environ['MYWEATHER_REFRESH'] = '1'
from _cache import cached_path
with open(cached_path("https://data.wymancove.com/weather_data.json", max_age_hours=0)) as f:
    wd = json.load(f)
for op in ("wg_residual_persistence", "dp_residual_persistence", "h_residual_persistence"):
    b = wd[op]
    print(f"{op}: regime={b['regime']}, fires={sum(b['fires_by_band'].values())}, "
          f"skips={sum(b['skips_by_band'].values())}, clamped={sum(b['clamped_out_by_band'].values())}")
```

Walker current state:
```python
import json
for field in ('h', 'dp', 'wg'):
    with open(f'/Users/josephselby/Documents/myweather/weather_collector/data/{field}_residual_persistence_walker.json') as f:
        w = json.load(f)
    print(f"{field}: cleared={w['n_cells_cleared']}, flipped={w['n_cells_flipped']}, days={len(w['days_in_window'])}")
```

Digest triage: `cat /Users/josephselby/Documents/myweather/analysis/output/DIGEST.txt | head -100` (or grep for "Verdict" / "HOT" / "τ-suspect").
