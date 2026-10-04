---
name: project-wg-residual-nbm-scope
description: "Scoping memo for wg_residual_persistence_nbm — NBM-side clone of the HRRR residual-persistence gate. Architecture: NBM cascade writes into forecast_snapshot entry dict, not hourly array, so the clone can't reuse the HRRR processor as-is. Prerequisite gate: HRRR wg_residual has to clear Stage 1 first (currently walker FAIL) — cloning a mechanism that doesn't work is a waste."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f584257-df4f-41a9-b227-c4bdf632ea0a
  modified: 2026-09-09T13:06:05.999Z
---

# wg_residual_nbm — scoping memo (09-09)

Exploratory only. No code shipped. Establishes what a working NBM residual-persistence gate would look like, what data it needs, and what has to happen before we build it.

## What the HRRR gate does (baseline mechanism)

Correction: in cells where `(regime, lead_band)` is SHIP or MARGIN in the curated JSON, replace the post-L3 `wind_gusts` value with `fc_l2 + hour_of_day_correction`, clamp to `[0, ∞)`. Gate is a **downgrade**: it discards L3 in fire cells and substitutes L2 + a per-clock-hour persistence add-on fit against prior 14d L2 residuals. Rationale: L3 bias fitting can over-correct at specific clock hours (diurnal pattern L3 doesn't see); a hour-of-day residual mean captures what L3 misses.

Currently Stage 3 wired `ENABLED=False` at `weather_collector/processors/wg_residual_persistence.py:21`. Whitelist streak walker: **FAIL** min-J 0.789 (worst diff: ne_flow/12-23, ne_flow/24-47, ne_flow/6-11, se_flow/12-23) per today's digest. Stage 1 flipped PROMOTE → MARGINAL 2026-07-26 and hasn't recovered.

## Architectural asymmetry — the actual blocker

HRRR wg_residual reads/writes `hourly.wind_gusts` (post-L3 array) + reads `hourly.wind_gusts_post_l2` (L2 stash). Runs as a standalone processor after decay_apply.

NBM cascade never touches `hourly.wind_gusts`. It writes per-lead into the pair-log entry dict inside `forecast_snapshot.py:915`:

```
entry[f"{f}_l3_nbm"]  # deepest layer per field
entry[f"{f}_wdp_nbm"]  # wd persistence NBM specialist
entry[f"{f}_chp_nbm"]  # ch persistence NBM specialist
```

The runtime writeback loop at `forecast_snapshot.py:929-969` picks the deepest available NBM layer when the selector routes NBM for that (field, lead) cell. Priority chain for wg: `l3_nbm > l2_nbm > raw_nbm`.

**Implication:** the NBM residual gate can't be a standalone processor in `weather_collector/processors/`. It has to write into the entry dict inside `forecast_snapshot.py`, alongside `chp_nbm` and `wdp_nbm`. The shared `_residual_persistence.py` harness assumes `hourly[hourly_key]` shape — it does NOT transfer.

## Three architectural options

**Option A — inline in forecast_snapshot.py, per-lead loop.**
Extend the per-lead loop (~line 780+) to compute `entry[f"wg_residual_nbm"] = entry["wg_l2_nbm"] + hour_of_day_correction[hour]` when regime × lead_band cell is SHIP/MARGIN. Add `wg_residual_nbm` to the priority chain ahead of `l3_nbm`. LOC estimate: ~40 lines in forecast_snapshot + curated JSON loader + describe_applicability. Closest match to existing chp_nbm/wdp_nbm shape.

**Option B — refactor the shared harness to be entry-dict-aware.**
Add an alternative code path in `_residual_persistence.py` that operates on a passed-in per-lead dict list instead of `hourly[hourly_key]`. HRRR wrapper unchanged; NBM wrapper calls the same harness with entry-dict shape. LOC: ~80 lines refactor + ~20 lines NBM wrapper. Cleaner but bigger surface — the semantic-preservation contract on the shared harness (v0.6.532 byte-diff) becomes harder to maintain across two shapes.

**Option C — shadow arrays.**
Have `forecast_snapshot.py` build per-lead arrays `hourly["wind_gusts_l3_nbm"]` + `hourly["wind_gusts_l2_nbm"]`, then run the existing HRRR processor over them with different hourly_key. Cleanest reuse but requires stashing arrays that nothing else needs, and gates against `weather_data.derived.state.regime_synoptic` — same regime for HRRR + NBM, so no per-source regime split, which we may want later.

**Recommendation:** Option A. Matches the existing NBM-specialist pattern (chp_nbm, wdp_nbm are both inline in forecast_snapshot). No refactor of the working HRRR harness. Trade-off: two implementations of the same mechanism to maintain.

## Data prerequisites — pair log

Stage 1/2 fit harness reads:
- `field == "wg"`
- `forecast_l2` and `forecast_{applied}` — **HRRR-anchored today**.

For NBM version, needs:
- `forecast_l2_nbm` — stamped in pair log since 2026-08-21 (per debug page "Pair-log depth" note). **~19 days of data as of 09-09.**
- `forecast_l3_nbm` — same accumulation window.
- `applied_layer_nbm` (or the existing `{field}_applied` when selector picks NBM) — the writeback at `forecast_snapshot.py:968` stamps `entry[f"{f}_applied"]` with the NBM layer name.

Fit requirements per HRRR Stage 1: `MIN_N_PER_REGIME = 300`, `TEST_WINDOW_DAYS = 7`, `DEFAULT_WINDOW_GRID = [1,2,3,5,7,14]`. NBM cascade data-availability today is thin at 14d window; **Stage 1 should have enough n by ~09-25** (36 days post native NBM-L2 shipping 08-26 v0.6.499).

## Prerequisite gate — HRRR wg_residual must clear first

HRRR wg_residual is Stage 3 wired `ENABLED=False`, walker FAIL as of today (min-J 0.789). Cloning a mechanism that doesn't work on HRRR data would be a false-lift attempt. Two futures:

1. **If HRRR clears** (walker Jaccard ≥ 0.8 sustained 7d, Stage 1 back to PROMOTE): the mechanism is real, the NBM clone becomes justified. Estimated clear window: unknown — Stage 1 has been MARGINAL since 07-26.
2. **If HRRR stays FAIL:** cloning is speculation. Kill the workstream on the NBM side too. Better use of the same time: NBM sea-breeze specialist (Lsb-analog) or NBM Kalman-K tuning.

**Decision rule:** don't build NBM residual gate until HRRR walker Jaccard passes for 7 consecutive days.

## Concrete file list (once prerequisite clears)

1. `analysis/l3_nbm_wg_residual_persistence_stage1.py` — thin wrapper on `_residual_persistence_stage1` with NBM pair-log field names + `forecast_l2_nbm` / `forecast_l3_nbm` read path. **Harness needs a source-aware parameter** — pass `field_prefix="l2_nbm"` and `applied_stamp="{field}_applied"` so it picks NBM residuals.
2. `analysis/l3_nbm_wg_residual_persistence_stage2.py` — same shape, writes to `weather_collector/data/wg_residual_persistence_nbm_curated.json`.
3. `analysis/l3_nbm_wg_residual_persistence_walker.py` — 7-day Jaccard walker over Stage 2's SHIP/MARGIN set. Reuses `_residual_persistence_walker` harness.
4. **No new processor file.** Correction lands inline in `forecast_snapshot.py` per Option A — ~40 LOC insertion into the per-lead loop + curated JSON loader at module scope.
5. `weather_collector/data/wg_residual_persistence_nbm_curated.json` — generated by Stage 2.
6. `analysis/runlog/build_executive_summary.py` — add `wg_residual_nbm` to the KNOWN_LIVE_PIPELINES / whitelist_streak entries when it ships.
7. `analysis/nbm_regression_sentry.py` — add `wg_residual_nbm` to the per-layer sentry list so post-ship regressions are caught.

## Open questions to resolve before starting

1. **Does the pair log actually stamp `forecast_l2_nbm` and `forecast_l3_nbm` per-row, or only `error_l2_nbm` and `error_l3_nbm`?** The Stage 1 harness needs forecasts, not errors. If only errors are stamped, need to backfill forecast columns in the joiner. Grep `weather_collector/*.py` for the joiner's field list — likely `update_forecast_error_log` in `collector.py:824`.
2. **Regime attribution — HRRR or NBM origin?** HRRR wg_residual uses `weather_data.derived.state.regime_synoptic` (obs-derived, source-agnostic). Fine for NBM version too; regime should be the same object regardless of which forecast source is being corrected.
3. **`applied_layer_nbm` naming.** Runtime stamps `{f}_applied` = `"l3_nbm"` (or wdp_nbm, etc.) when selector picks NBM per `forecast_snapshot.py:968`. The Stage 1 harness reads `applied_layer` (HRRR-anchored). Either extend harness with an `applied_source` parameter or accept that the NBM Stage 1 will need a different attribution branch. Preferred: harness parameter.
4. **Firing gate against selector state.** wg_residual_nbm should only fire on cells where the selector routes NBM. Otherwise we're wasting compute writing corrections nobody consumes. Add pick_source check inside the per-lead loop.

## Estimated effort (from HRRR clear to NBM ship)

- Stage 1 fit + walkforward: 1 session, gated by 30+ days of NBM cascade pair-log data (~09-25 earliest).
- Stage 2 curated + halves check: 1 session, 7 days after Stage 1 clears.
- Stage 3 inline wire in forecast_snapshot: 1 session, ~40 LOC + curated JSON loader + describe_applicability + tests.
- 7-day walker + shadow watch: 1-2 weeks.
- Ship-day: `ENABLED=False → True` one-line flip + redeploy.

**Total elapsed: ~3-4 weeks from HRRR clear.**

## Alternative next-workstream candidates (if HRRR wg_residual stays FAIL)

Ranked by lift potential given today's per_field_scoring gaps:

1. **NBM sea-breeze specialist (Lsb-analog for wd, sr, t).** No HRRR analog to gate on — pure new work. High potential lift because sea-breeze is a distinct regime with directional bias signatures. Prerequisite: `sea_breeze` regime detector already exists; harness is Stage 0 exploration of NBM residual by clock-hour × sea_breeze subset.
2. **NBM ch Lc-analog (cloud-saturation correction).** NBM only ships ch (not cl/cm), so structurally simpler than HRRR Lc. Small surface, small ship, real lift on the ~10% of ch corr the NBM cascade is leaving on the table.
3. **NBM L2 Kalman-K per-field tuning.** v0.6.499 shipped native L2 math with copied HRRR Kalman gains. Refit against NBM's own residual distribution — 1-session ship if the fit shows lift.

## Related

- [[project_wg_residual_persistence]] — HRRR gate lineage
- [[project_wg_l3_regression]] — the L3 regression that motivated the HRRR gate
- [[project_nbm_parallel_pipeline_plan]] — plan doc; residual specialists not covered
- [[project_09_09_digest_watches]] — l3_nbm ADD wd walkforward proposal, adjacent workstream
- [[feedback_whitelist_promotion_gate]] — 7-window gate applies to NBM version too
