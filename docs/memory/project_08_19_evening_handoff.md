---
name: 08-19-evening-handoff
description: 2026-08-19 evening handoff. Afternoon session shipped v0.6.441 (Right Now values-only restoration + Base forecast (L1) column) and v0.6.442 (collector stamps hourly.l1_selected_* + full debug-page scoring rebuild with grouped column headers + scoreboard band redesigned as 3-tile headline strip + National Source Score + Health & Reliability). Pushed to GitHub. READ-FIRST for tomorrow morning.
metadata: 
  node_type: memory
  type: project
  originSessionId: c4abe134-966d-4faf-978d-a5fc16044c53
  modified: 2026-08-20T02:45:27.926Z
---

# 08-19 evening handoff — scoring surfaces rebuilt end-to-end

**Supersedes** [[08-19-afternoon-handoff]]. Read this first tomorrow morning.

## What shipped (v0.6.441 → v0.6.442, committed efccb4b, pushed)

### v0.6.441 — Right Now restoration
- `renderScoreboardV2()` no longer clobbers `#headlineBox`; `renderHeadlineBox()` owns hbCorrRows again
- Right Now table is 2-col × 7-row values-only: `Field | Base forecast (L1) | Production | Correction`
- Header renamed "Right now — current conditions"
- Footnote calls out what Base forecast / Production / Correction each mean
- National Source Score tile deleted (later reintroduced in new form)
- `analysis/per_field_scoring.py` NEW — publisher CF wires it in as an hourly job
- New per-field scoring table under Current-state header

### v0.6.442 — L1 selector-aware collector + full page rebuild
- **Collector**: `forecast_snapshot.py` stamps `hourly.l1_selected_{field}` arrays (14 fields, 48 leads) — element i = raw of whichever source the selector picked at that lead. Selector-aware truth for the debug page's Base forecast column.
- **`renderHeadlineBox`** reads `hourly.l1_selected_{field}[0]` per field with legacy fallback. Also fixes the h "raw" bug (was `h_cor − L2_bias` which silently absorbed L4 diurnal).
- **Per-field scoring table**: grouped column headers (Public inputs / Wyman Cove L1 chooser / Wyman Cove correction stack / Total result) with color-coded stage labels. Columns: HRRR MAE | NBM MAE | L1 MAE | Chooser lift | Prod MAE | Local lift | Production lift. 7d primary + 24h below in each cell. Row markers "7d/24h" at right edge of Field cell. Units in field label, not repeated per cell. Halves-disagree ✗ glyph on lift cells (silent when halves agree).
- **Scoreboard band redesign** (replaces earlier 4-tile band): 3-tile headline strip (L1 chooser lift / Local lift / Total result — each with per-stage winning/flat/losing counts AND field lists) + National Source Score tile + Health & Reliability tile. Verdicts row ripped (redundant with strip counts, different thresholds and vocab).
- **Per-metric field sets** (final): Chooser lift over 7 NBM-scope fields (t/h/ws/wg/wd/ch/sr); Local + Total over 11 (adds cl/cm/pp/pr). Excludes only derived (cc, dp) and pa (denominator near zero in dry windows). pp is L1-only today so local lift = 0.0% for it — honest signal, not hidden.
- **Vocab standardization**: "winning / flat / losing" everywhere on scoreboard surfaces. Enforced via new memory [[scoreboard-vocab-winning-losing-flat]].

## Live state at handoff (2026-08-19 23:20 UTC)

- **Collector**: v0.6.442 deployed and stamping `hourly.l1_selected_*` arrays cleanly (verified 14 keys, length 48, `l1_selected_t[0] = 82.9`)
- **Publisher CF**: `per_field_scoring` in PUBLISHERS list; `per_field_scoring.json` published; **halves_agree block is `None` in current JSON** because my late halves-compute change hasn't refit yet — self-heals next hourly publisher run (:00 UTC)
- **Scoreboard v2 JSON**: still emitted; consumed only for National Source Score + Health & Reliability tiles now
- **Pair log**: `error_l3_nbm` accumulating for all 9 NBM fields since v0.6.440 (~10:41 UTC 08-19); `error_l1` / `error_{applied}` on HRRR side going back weeks
- **L1 selector table**: still all-HRRR fallthrough (chooser hasn't fired NBM in any cell yet); expected until ~09-17 without backstamp
- **NBM backfill CF**: idle at 44% (1,127/2,568 hours); downsized to 2vCPU/4GB

## Numbers to sanity-check tomorrow morning

Current 7d values (from per_field_scoring.json 23:01 UTC refit):
- t: hrrr 1.63 / nbm 2.44 / L1 1.63 (chooser fallthrough) / prod 1.59 → sel_n +33% (HRRR was right pick), corr +2.2%, total +2.2%
- dp: hrrr 2.89 / nbm 1.55 / L1 2.89 / prod 2.67 → sel_n -87% (chooser missed NBM), corr +7.5%, total -72%
- ch: hrrr 28.3 / nbm 21.4 / L1 28.3 / prod 11.0 → sel_n -32%, corr +61%, total +49% ← correction stack heroing
- sr: hrrr 103 / nbm 62 / L1 103 / prod 91 → sel_n -66%, corr +12%, total -45%

Story: L1 chooser losing on the fields where NBM would win; local stack is doing real work on top; total pipeline is winning on ch/cm/wg and losing on dp/sr/wd (all cases where the chooser flipping to NBM should fix it).

## Known-broken (small)

1. **halves_agree = None in the current per_field_scoring.json** — publisher CF hasn't refit with the new compute yet. Fixes at next :00 UTC. Until then, the ✗ glyphs never fire and the Halves-agree line reads "—".
2. **`selector_source` field on entry stamp** — verified on new hours only (post-v0.6.442 collector). Historical hours in forecast_log.json don't have it, so any retrospective analysis needs to handle its absence.

## Backfill status (as of 02:45 UTC 08-20)

**Partial progress: 1127 → 1198 blobs (+71).** Target 2,568. **Not going to finish overnight — needs your call in the morning.**

What happened:
- Attempt 1 (`parallel=20`, num_days=108): OOM immediately (4GB ceiling).
- Attempt 2 (5-chunk chain, `parallel=8`): all 5 OOMed on cycle-start (default `cycle_parallel=8` was multiplying — actual concurrency 8×8=64).
- Attempt 3 (5-chunk chain, `cycle_parallel=2 lead_parallel=4`): chunks 1-2 ran successfully but each only added ~35 blobs in the full 55-min CF window. Chunks 3-5 401'd because my identity token (captured at chain start) expired after ~60 min. Net +71 blobs in ~2 hours.

Rate at current safe-memory settings ≈ 0.65 blobs/min → 1370 remaining blobs ≈ 35 hours. Too slow.

**Two paths for tomorrow (needs your call):**

A. **Bump backfill CF back to 8vCPU/8GB temporarily** (reverses this morning's cost-audit downsize). Cost delta: ~$0.60/invocation × 5 chunks ≈ $3 total. Full throughput → backfill completes in ~90 min. Then revert to 2vCPU/4GB. `make deploy-nbm-backfill` with edited memory arg.

B. **Find the sweet spot at 4GB** — probably `cycle_parallel=4 lead_parallel=6` (24 concurrent decodes). Not tested tonight due to OOM risk without your input.

Recommend A for speed. If picking B, also chain with fresh identity-token refresh between chunks (my chain used a single stale token).

Backfill CF is otherwise healthy — writes to persistent per-hour blobs at `gs://myweather-data/nbm_backfill/` as designed.

## Parked for tomorrow (in priority order)

1. **Publisher CF redeploy** — required to pick up `per_field_scoring.py` in PUBLISHERS list + the halves compute. Without this, `per_field_scoring.json` on GCS stays frozen at my 23:01 UTC force-publish (no halves). `make deploy-publisher` or equivalent.
2. **NBM backstamp script** — top priority once backfill completes. Retro-computes `error_raw_nbm` + `error_l2_nbm` + `error_l3_nbm` for historical pair-log rows using backfilled NBM raw blobs. Feeds `analysis/l3_nbm_fit.py` (which has NEVER fit — see NBM L3 fit status tile: "Last fit: never · 0 pairs in window"), then `analysis/l1_selector_fit.py`. Full chain unblocks the chooser flipping cells this week instead of 09-17.
3. **Per-stage halves-agree in Health tile** — currently one aggregate halves-agree line; splitting to `Chooser X% · Local Y% · Total Z%` was discussed and not shipped. Small change.
4. **Chooser lift is 0.0% for t/ws (not shown as `—`)** — Python printer treats `0.0 or "—"` as `—` which is misleading in dev output; live JSON has 0.0 correctly. Not a shipped bug, just a scratchpad print quirk.

## Order of operations tomorrow morning

1. Check backfill blob count (`gsutil ls gs://myweather-data/nbm_backfill/ | wc -l` — target 2,568). If short, chain another invocation with parallel=8.
2. Deploy publisher CF (`make deploy-publisher`) so hourly refits include halves + per_field_scoring.
3. Write NBM backstamp script (parked #2 above).
4. Fit L3_NBM against backstamp-fed pair log.
5. Fit L1 selector against L3_NBM output.
6. Watch chooser start flipping cells in per-field scoring table.

## Communication lessons this session (Claude-directed)

Long, painful session. Real lessons that need to stick:

- **Vocab drift**: introduced beat / improved / regress / winning / losing on the same page in a single session. New memory [[scoreboard-vocab-winning-losing-flat]] pins the triplet forever. Do not silently pick a new bucket word.
- **Over-narration**: talked through every option every step. Joe wants me to just build and show, not lecture. When in doubt, act; when the mock is clear, don't restate it.
- **Copy-paste field sets**: reused AGG_FIELDS for all three lift metrics without asking whether each metric was defined on those fields. Chooser lift on cl/cm is always 0% (no NBM alternative). Per-metric domain check before typing.
- **UI iteration without style guide**: 8+ visual iterations on the per-field table before landing. Joe called this out multiple times ("looks like shit", "you're insane"). See [[feedback_ui_incremental_drift]]. Get typography + width convention right FIRST, then fill in content.
- **Confused L1 semantics early**: initially treated L1 as "raw HRRR" and had to be corrected repeatedly that L1 = post-chooser. Now the whole page reflects this correctly, but the confusion cost real time.
- **Assumed 30-day wait was inherent**: quoted "chooser can't flip until ~09-17" without asking whether we could shortcut with historical data. Joe pushed back correctly — the backstamp is a real move. Parked as tomorrow's top priority.

## Files touched (commit efccb4b)

- `corrections_debug.html` — Right Now restoration, new per-field scoring table, scoreboard rebuild, all new CSS (~750 lines net delta)
- `index.html` — v0.6.442 pill
- `publisher/main.py` — added `per_field_scoring` to PUBLISHERS
- `sw.js`, `version.json` — cache-bust bumps
- `weather_collector/processors/forecast_snapshot.py` — stamps `hourly.l1_selected_{field}` arrays
- `analysis/per_field_scoring.py` — NEW compute + publisher

## Reference

- [[08-19-afternoon-handoff]] — earlier state, superseded
- [[08-19-morning-handoff]] — even earlier, superseded
- [[pair-log-dual-source-schema]] — post-Phase-4 pair-log fields
- [[scoreboard-vocab-winning-losing-flat]] — enforce the triplet
- [[feedback_selector_prod_vs_prod]] — Prod-vs-Prod design rule from morning
- [[feedback_ui_incremental_drift]] — style-guide-first
