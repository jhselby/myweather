---
name: 08-20-evening-handoff
description: "2026-08-20 evening handoff. Backfill CF finished at 2,455/2,568 (95.6%, rest are NOAA archive 404s). Shipped v0.6.443-446 (debug page polish) + v0.6.445 (NBM backstamp tool + L3_NBM fit + L1 selector fit — 9 cells flip to NBM: wg 12-47h, dp 6-47h, cc all leads). Collector deployed and picking correctly as of tick 00:47 UTC. READ-FIRST for tomorrow morning."
metadata: 
  node_type: memory
  type: project
  modified: 2026-08-21T00:57:05.765Z
  originSessionId: baca9c78-976c-4017-bfd2-0d70ba565f71
---

# 08-20 evening handoff — NBM chooser is LIVE

**Supersedes** [[08-19-evening-handoff]]. Read this first tomorrow morning.

## What shipped (v0.6.443 → v0.6.446, all pushed to main)

- **v0.6.443** — debug page: blanked 5 stale Selector-picks cells (t/h/ws/wg/wd) in per-field pipeline architecture (leftover v0.6.432-router bands from before the v0.6.440 rewrite).
- **v0.6.444** — debug page: unified all 9 warming Selector cells to `"warming — see live table below"` (was mix of "pending first fit" and "warming").
- **v0.6.445** — **NBM backstamp shipped end-to-end.** New `analysis/nbm_backstamp.py`. Fresh `l3_nbm_curated.json` (373/384 cells, was 0/192). Fresh `l1_selector_table_curated.json` — **9 cells flip to NBM: wg 12-47h, dp 6-47h, cc all leads.** Router-scope ship-gate NBM lift +8.5% on n=74,528.
- **v0.6.446** — debug page: Selector-picks column now data-driven from the same JSON (ends drift risk).

## Live state at handoff (2026-08-21 00:55 UTC)

- **Backfill CF:** DONE at 2,455/2,568 blobs (95.6%). Remaining ~110 are 404s from NOAA's NBM archive — permanently missing cycles, not our problem. CF reverted to 4096M/2CPU per cost-audit (Joe ran `make deploy-nbm-backfill` at 00:07 UTC). No wave 10 needed.
- **Publisher CF:** Deployed tonight; `per_field_scoring.json` refits hourly with halves compute.
- **Collector CF:** Redeployed 00:39 UTC. First post-deploy tick at 00:47 UTC ran clean. `forecast_log.json` verified — 36 NBM/selector keys per hourly row, `wg_selector_source` / `dp_selector_source` / `cc_selector_source` firing as expected per curated table.
- **User-visible impact:** wg 12-47h now delivered from NBM cascade. dp 6-47h delivered from NBM cascade. cc all leads delivered from NBM cascade.

## ⚠️ Bug queued for next session

**cc `l3_nbm` can exceed 100%.** Verified in latest snapshot: leads 4-7 all show `l3_nbm=100-101` (raw NBM cc=94-95 + L3 bias ~+6 pushes above physical max). Users may see 101% cloud cover on the app. Fix is a `min(100, l3_nbm)` clamp at the cc apply site in `forecast_snapshot.stamp()` — probably needs mirror clamp for cl/cm/ch too. Small edit, one line each. Do this BEFORE L4_nbm work.

## Backstamp method — reusable pattern

Documented for the ~4 remaining NBM-layer ships. See `analysis/nbm_backstamp.py`.

Key insight: **L2_nbm can be reconstructed exactly from historical pair-log rows** without needing live Kalman state, because the pair log snapshots `forecast_l1` (raw HRRR) and `forecast_l2` (post-Kalman HRRR) at forecast time. The Kalman delta = `forecast_l2 - forecast_l1`. NBM L2 uses the same delta by design → `l2_nbm = raw_nbm + delta`. This defeats the earlier design-decision comment in l3_nbm_fit.py that said "L2 residuals depend on live Kalman state, snapshotted only in pair log" — TRUE for LIVE stamping, but reconstructible retroactively via the pair-log snapshot.

**Two-pass pattern** (essential):
1. Pass 1 backstamp with L3 identity (l3_nbm = l2_nbm). Fits L3.
2. Pass 2 backstamp reads the freshly-fit L3 curated JSON, applies bias. Fits L1 selector against L3-corrected residuals.

For NBM-scope fields WITHOUT HRRR L2 (ch/sr/dp/cc): `l2_nbm = raw_nbm` passthrough. No delta reconstruction needed.

**Cache-swap trick** to point existing fitters at the backstamped log:
```bash
cp ~/.cache/myweather/forecast_error_log.jsonl ~/.cache/myweather/forecast_error_log.jsonl.orig
cp ~/.cache/myweather_nbm_backstamp/forecast_error_log_backstamped.jsonl ~/.cache/myweather/forecast_error_log.jsonl
python3 -m analysis.l3_nbm_fit
python3 -m analysis.l1_selector_fit
cp ~/.cache/myweather/forecast_error_log.jsonl.orig ~/.cache/myweather/forecast_error_log.jsonl  # restore
```
No need to modify fitters or add env var support. `_cache.cached_path` returns local path when TTL not stale.

## Parked for next session (in priority order)

1. **cc >100% clamp bug** — 5-minute fix, ship before L4 work. Also verify cl/cm/ch don't have the same issue.
2. **L4_nbm ship** — mirror `l4_diurnal_fit.py`, extend `nbm_backstamp.py` to synthesize `error_l4_nbm`, fit, ship. Same-session maturity via backstamp. Per Joe: get right to L4 unless digest surfaces something urgent.
3. **Cross-cutting per-ship infra** (bundled with L4):
   - KNOWN_LIVE_PIPELINES registry entry for `l3_nbm` (avoid digest "auto-relabeled STABLE" flap)
   - Divergence report key `L3_NBM_FIELDS`
   - Walkforward validator learns NBM-side cell membership
   - Stratify existing HRRR-cascade hypothesis fits by `selector_source` — starts mattering now that NBM picks land in the pair log; mixed-source bins can contaminate HRRR-side fits going forward.
4. **L5_nbm, L6_nbm, then specialists** (chp_nbm, dpbp_nbm, Lc_nbm, Lsb_nbm). Skip Lt_nbm (retired HRRR-side) and cc_combine_nbm (NBM doesn't publish cl/cm to combine from).
5. **Debug page full staleness sweep** — Joe flagged after we caught the Selector-picks drift. Do a pass through `corrections_debug.html` for outdated prose: stale version numbers referenced in narrative, "warming up" / "pending first fit" language on tiles that are now live (NBM L3 tile should update — 373/384 filled), "ETA ~09-17" language for the selector arm (which shipped tonight), any references to v0.6.432 router as if still live (was ripped in v0.6.440), narrative on the per-field pipeline cells that still describes pre-flip state, etc. Grep for `warming|pending|expected|ETA|09-17|v0.6.432|v0.6.436` and cross-reference each hit against current live state. Per [[feedback_debug_page_full_sweep]].

Plan-of-record cross-ref: [[nbm-parallel-pipeline-plan]] (2026-08-20). Full parallel cascade, not source-late. ~4 sessions remain to full parity.

## What to expect on the debug page as data ages

- **Right now (hard-reload):** L1 selector table shows 9 NBM cells. Per-field pipeline architecture Selector column shows live picks (data-driven per v0.6.446). L3_NBM fit-status tile shows 373/384 filled.
- **Within ~1 hour:** per-field scoring table's `n_nbm` selector-picks counter starts growing for wg/dp/cc (was 0 across the board).
- **Within ~24 hours:** 24h row of the per-field scoring table shows real chooser-lift numbers on the NBM-picked cells.
- **Within ~7 days:** 7d row stabilizes. Scoreboard headline strip's "L1 chooser lift" tile shows meaningful aggregate.

**Expected accounting pattern** as chooser flips take hold: L1 chooser lift on wg/dp/cc → positive, Local lift on those fields → shrinks toward small L3-only contribution (NBM-side stack is thin — 2 layers vs HRRR's 5-6), Total result → grows. Every future L*_nbm ship moves value from "chooser lift" back into "local lift" and may flip more cells NBM.

## Communication lessons this session (Claude-directed)

- **Over-narration during long tool sequences** — kept giving big status paragraphs. Joe interrupted twice ("oy", "whoa"). Shorter updates during execution; save the paragraph for verdicts.
- **Design decisions surface** — the "L1 selector picks based on Prod-vs-Prod, not Raw-vs-Raw" question already had a settled answer in memory ([[selector-prod-vs-prod]], [[nbm-parallel-pipeline-plan]]). Joe asked "did we decide to run parallel not source-late?" — the answer was in memory. Should have led with that instead of re-deriving. Read memory more aggressively when Joe asks confirmation questions.

## Files touched (commits 50b80ee, 44c449c, e8f116e, 8a57904)

- `corrections_debug.html` — 3 iterations on Selector-picks cells (v0.6.443/444/446)
- `analysis/nbm_backstamp.py` — NEW, two-pass backstamp tool
- `weather_collector/data/l3_nbm_curated.json` — full 373/384 cell fit
- `weather_collector/data/l1_selector_table_curated.json` — Prod-vs-Prod fit, 9 NBM cells
- `index.html`, `sw.js`, `version.json` — v0.6.443 → v0.6.446 bumps
- `docs/CHANGELOG.md` — 4 entries

## Reference

- [[08-19-evening-handoff]] — superseded, kept for chronology
- [[nbm-parallel-pipeline-plan]] — plan of record, still current
- [[selector-prod-vs-prod]] — design rule enforced tonight
- [[pair-log-dual-source-schema]] — schema this ship extended
- [[scoreboard-vocab-winning-losing-flat]] — enforced this session
