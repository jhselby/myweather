---
name: project-08-02-session
description: "2026-08-02 session log. 4 ships (v0.6.390o/p/q/r + follow-on s). Marquee: two metric-plumbing bugs found and fixed that had been silently hiding truth for days-to-weeks. (1) cl regression sentry firing loud (+67% 7d) was pair-log applied_layer poison from the pre-v0.6.390j shadow-write bug; wrote analysis/backfill_cl_applied_layer.py one-shot re-stamper. (2) wd looked chronically L1-forever because mae_over_time L1_ONLY branch was reading L2-view `error` as raw, hiding L2+wdp contributions for 13 days since v0.6.368a. Also: scoreboard 'today' column reworked to rolling last-24h (always full diurnal cycle); every scoreboard tile now shows 7d + 24h stacked; full Rule 5 debug-page sweep."
metadata: 
  node_type: memory
  type: project
  originSessionId: 49547252-cd8d-4eff-b0cf-640d7facf514
  modified: 2026-08-02T13:02:45.627Z
---

# 2026-08-02 session

**4 ships + 1 follow-on. Session theme: honest metrics. Two silent-lie bugs caught and fixed.**

## Ships in order

- **v0.6.390o** — cl applied_layer poison backfill + L1_ONLY routing fix + full debug-page sweep. Marquee ship. See "Silent lies" section below.
- **v0.6.390p** — per-field snapshot "today" → rolling "last 24h" (always contains full diurnal cycle). Joe caught the AM-easy bias: at 7am, "today" is 7h of overnight-only data — every field looks artificially good. Rolling 24h always has one complete cycle. See [[feedback_rolling_24h_over_calendar_today]] NEW.
- **v0.6.390q** — KPI tile static text "today" → "last 24h" (missed by 390p — static initial HTML flashed "today" before JS updated).
- **v0.6.390r** — scoreboard 24h subs on Biggest gain / Biggest field regression / Worst cell tiles. Only Overall-mean had 24h before; now every tile pairs 7d + 24h. Required emitting `last_24h_bands` per (field, band, layer) from `mae_over_time.py`.
- **v0.6.390s** — 24h tiles show "✓ no field regressing" wins-state instead of "—" when clean. Dash reads as missing data; explicit statement reads as truth.

## Silent lies (both metric-plumbing bugs, both fixed)

### 1. cl "regression" was pair-log poison

Digest was firing `cl: SUSTAINED FIRE — 7d +67.5%` daily. Joe: "cl is terrible right now and it was good yesterday." Investigation: cl production forecast was **actually fine**. The digest reads `mae_over_time.prod_real` which reads `error_{applied_layer}` per-row. Pre-v0.6.390j shadow-write bug had left 5,834 cl pair-log rows stamped `applied_layer=clp` (or `l6`) even though clp/Lc weren't running for cl. For those rows, `error_clp` was a phantom shadow value (~49) while `error_l1` = `error` = real production (~21). `prod_real` pulled the phantom.

v0.6.390j had guarded the STAMPER forward; it didn't clean the historical stamps that keep poisoning the 30-day rolling pair log.

**Fix:** wrote `analysis/backfill_cl_applied_layer.py` — mirrors `_derive_applied_layer`'s value-walk against per-layer errors to re-stamp cl rows. 5,834 poisoned rows re-stamped (2,283 clp + 3,540 l6 → 5,779 l1 + 55 l2, 0 unresolved). Rebuilt mae_over_time.json with `MERGE_REFRESH_DAYS=10` to overwrite the poisoned window and re-uploaded to GCS. Regression sentry now clean. cl reads 7/7 wins at −1.1% vs raw. Backfill script is parameterizable for future dpbp/wsbp flips through the same trap. See [[feedback_shadow_write_applied_layer_trap]] updated with historical-poison cleanup recipe.

### 2. wd looked L1-forever because mae_over_time was reading L2-view as raw

Joe: "wd is not L1 forever." Investigation: `mae_over_time.py`'s `L1_ONLY_FIELDS = {"wd"}` branch routed top-level `error` into the `raw` bucket. But `error = fc − obs` and `fc = wd_l2` (per forecast_snapshot's L2-default rule since v0.6.368a). So `raw` and `l2` were bit-identical every day for 13 days — L2's wind_blend contribution invisible in every field-health scoreboard. No `prod_real` for wd either (L1_ONLY doesn't get applied_layer stamping).

**Fix:** L1_ONLY branch now prefers `error_l1` (post-v0.6.368a wd rows have it from the `raw_wind_direction` stash). Emits inline `prod_real` from the deepest specialist present (wdp > l2). Real wd picture surfaced: L2 −2 to −5% vs raw most days, wdp adds another 0-4%. **07-31 outlier** now visible: calm/24-47 wdp +72%, sea_breeze/0-5h wdp +109% — real gate misfires; if either recurs, narrow wdp gate; else close clean at 08-10 watch end. See [[feedback_l1_only_field_routing_trap]] NEW.

## Scoreboard framing improvements (Joe's driver)

Joe pushed hard on framing throughout the session:
- **"Don't massage numbers to look good when fields aren't actually winning."** I'd been cherry-picking best daily numbers under a losing 7d average. Corrected framing: report the losing 7d as red, note trend direction as separate signal, verdict date is the point of decision.
- **"Even a chronic 1% win is a track record if it's every single day."** `t` field is −1.6% vs raw with 7/7 wins — that's green, not "neutral near raw." Any field consistently beating raw is a win, however small. Updated per-field narratives accordingly.
- **"There are only 3 trend states: getting better, getting worse, staying the same."** No hedging into "mixed" or "neutral" when the direction is readable. Recent 3d vs prior 4d comparison quantifies it.
- **Scoreboard needs both cadences at every tile.** 7d catches sustained drift; 24h catches fresh single-day movements the 7d smooths over. Symmetry is important.

## Fossil-window slides

Slid `h_wg_l3_regression_stage1`, `h_ws_l3_regression_stage1`, `h_ch_persistence_blend_stage2_vs_l6` — all had WIN_A_HI stuck at 07-28 (flagged as fossils in the morning digest).

## Debug page full Rule 5 sweep

Calendar block had "Thu 07-30 · today" (3 days stale) — rewrote with 08-02 as today plus correct upcoming rows. Recent Activity labels bumped; ~15 day counters across Post-ship watches updated. Per-field snapshot narratives rewritten to honest green/red framing (no cherry-picking). Bottom summary line rebuilt.

## Not done this session

- **Fitter run left on natural cadence** (15:07 UTC). 7d scoreboard tiles show stale +58.9% cl / +75.3% cl@24-47h from morning Fitter tick (03:08 UTC, pre-backfill). Will refresh on next tick. Joe chose to wait.
- **build.py has a subtle bug**: it pattern-matches `Day N/14` near a version substring to auto-bump counters. When two versions share a paragraph (e.g. wd L2 v0.6.368a + wdp v0.6.382 in the same td), it can update the wrong counter. Caught + manually corrected line 909 mid-session. Not filed as a repo issue; worth flagging if it recurs.

## Memories updated this session

- [[feedback_shadow_write_applied_layer_trap]] — added historical-poison cleanup recipe + reference to backfill script
- [[feedback_l1_only_field_routing_trap]] NEW — audit any new L2+ correction on an L1_ONLY field for the raw-routing pitfall
- [[feedback_rolling_24h_over_calendar_today]] NEW — architectural principle for dashboard "today" columns
- [[feedback_scorecard_banner_shape]] — updated to reflect 7d + 24h stacked shape

## Standing action items after this session

- 08-03: chp full-shape refinement + clp gate close
- 08-04: h L2 retune verdict + ws recovery verify + Lsb / dpbp / wsbp / wg L3 re-cut close (multi-gate day)
- 08-06: Lc regime-conditional Stage 1 gate close
- 08-07: h L2 retune 7-day watch close
- 08-10: wdp 14-day watch close (narrow if 07-31 outlier cells recur)
- 08-11: wg L3 4-cell + ws L3 2-cell + wind_blend BLEND_HOURS 14-day watches close

All red fields have interventions in flight with verdict dates. No unaddressed regressions.
