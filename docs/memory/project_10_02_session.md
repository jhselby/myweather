---
name: project-10-02-session
description: "10-02 session. 2 ships: v0.7.20 first L1-static-blender apply-flip (h/nw_flow/24-47, narrow via APPLIED_CELLS) + v0.7.21 measurement-trap fix (applied rows invalidated the verifier's served baseline) + writeback allowlist completion. v0.7.19 sr learned_gbm attribution CONFIRMED. Both ships UNDEPLOYED at session end."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-02T14:10:00.000Z
---

# 10-02 session

## State at session end — ALL THREE SHIPS DEPLOYED/PUSHED AND COMMITTED ✅

- **v0.7.20** deployed rev `00606-mak` 08:33:06 EDT — verified firing (see below).
- **v0.7.21** deployed rev `00607-poj` 18:42:21 EDT — 4 clean ticks, cold start 47.1 → 468.2 MiB, shadow telemetry intact (132 h / 134 dp stamps).
- **Committed + pushed** as `c79c68dc` (one commit covering both; version/changelog files only carry the final v0.7.21 state so they couldn't be split). Plain `git push`, 7 files. Daily digest churn deliberately NOT staged — ship commits in this repo carry code + version + changelog only, matching v0.7.19's 5-file shape.
- **v0.7.22 — debug page full sweep**, commit `020cda9a`, frontend-only (no collector deploy). Added 10-02/10-01/09-30 to Recent Activity (page still showed 09-29 as "today"); de-staled the blender state in both places it appears; rebuilt the calendar around the shipped flip; killed the dead "sr has no cells" claim that was steering the 10-03 verdict. **Found a leftover from an earlier incomplete sweep:** 09-15 was labelled "trimmed" without `display:none`, and 09-14 / 09-12 were rendering as "1 day ago" / "2 days ago" — 18 and 20 days stale. `make check-stale` does not catch these (historical, not predictive-tense) and they survived several sweeps because they look plausible on skim. **Worth a dedicated check next sweep: grep the Recent Activity list for visible `<li>` entries and confirm each relative-date label matches the actual date.**

**Still unobserved end-to-end:** the `{f}_preempted_source_shadow` stamp on a real applied row, and the writeback (`hourly.corrected_humidity` at an applied lead == the stamped blend). Both need an `nw_flow/24-47` hour. It hit 1 of 5 ticks in the morning and 0 of 4 in the evening — genuinely intermittent. The trap fix is in place *before* it could bite, which was the point.

## Scheduled verifies — results

- **v0.7.19 sr `learned_gbm` attribution: ✅ CONFIRMED.** Weather rotated into sw_flow overnight. Post-deploy pair-log (run_time ≥ 10-01T13:00, n=186 sr rows): **50 `learned_gbm` / 136 `band_pool`**, all 50 landing exactly on `sw_flow/6-11` — one of the 5 covered cells. Every non-covered cell `band_pool`. Three ships (v0.7.15 → v0.7.18 → v0.7.19) to get one classifier firing. [[feedback_shipped_flag_verify_effect]] earned its keep a third time.
- **v0.7.17 wg/nw_flow/12-23h: still weather-pending.** Zero wg nw_flow 12-23 pairs with run_time after the 09-29 deploy. Corroborating only: `nbm_regression_sentry` flipped kill→info, wg.l3_nbm HOT cleared.
- **v0.7.6 nw_flow/24-47 narrow flip: gate cleared → shipped as v0.7.20.** Shadow verify went 2 SHIP-READY / 13 HOLD / 7 KILL / 7 THIN (09-29) → **9 / 10 / 1 / 0**. The pre_frontal KILLs that blocked a wider flip collapsed to HOLD; only `dp/pre_frontal/12-23` still KILLs.
- **cc FRESH FIRE: resolved as artifact.** cc gone from the regression sentry entirely. The lucky-baseline read was right.

## v0.7.20 — first blender apply-flip, narrow

`h/nw_flow/24-47` only: n=436 (gate min_n_rows=400, crossed today), lift +35.5%, halves **38.7 / 33.9** — tightest spread of the nine SHIP-READY cells.

**Deviated from the debug page's written plan on purpose.** `corrections_debug.html:2320` said to strip `l1_static_blend_curated.json` down to nw_flow/24-47 cells and set `ENABLED=True`. That would have destroyed shadow telemetry for the other 19 cells and with it the 10-03 verdict corpus. Instead: `ENABLED=True` **plus** a per-cell allowlist `APPLIED_CELLS = {"h": {("nw_flow","24-47")}}`, gated by new `is_applied(field, regime, band)`. All 20 cells keep stamping. Reversal = `APPLIED_CELLS = {}`.

`dp/nw_flow/24-47` **held** — same n=436 and lift gate cleared (+17.5%) but halves 7.7 / 42.4 too wide to flip same-day.

**Load-bearing companion fix.** `_SELECTOR_WRITEBACK` only wrote back on `selector_source == "nbm"`, so an applied `l1_blend` row would have put the blend in `entry[f]` (snapshot + pair log) while `hourly["corrected_humidity"]` — what the PWA serves — kept the HRRR L4 value. **Would have scored the cell at +35% on a number users never saw.** Same class as F6 (2026-08-21) for NBM picks.

**Verified firing same-day** (I had predicted it would be inert — wrong). 08:57 tick, 9 applied rows, leads 24–29 and 43–45, all in-band. `entry[h] == {h}_l1_blend_shadow == 0.44·l1 + 0.56·raw_nbm` exactly on all 9. Firing is intermittent — only that one tick of five had nw_flow at 24–47h.

## v0.7.21 — the measurement trap (the real find)

**An apply-flip silently invalidates the very verifier that justified it.** `l1_static_blend_shadow_verify.py:195` took `served_mae` from `row['error']`. Once the cell applies, served *is* the blend, and since every shadow-stamped row in that cell is also an applied row, `served_mae == blend_mae` → lift exactly **0.0%** → cell drops SHIP-READY (+35.5%) → **HOLD at 0%** the day after shipping. Demonstrated: same synthetic cell reads `SHIP-READY (+80%)` with the fix, `HOLD (+0%)` without.

**Root enabler:** the apply block overwrote `entry[f"{f}_selector_source"]` with `"l1_blend"`, erasing the only record of the counterfactual. `selector_mechanism` survives but names the rule, not the source. v0.7.0's `blend` path had the same overwrite.

**Fix:**
1. Stamp `{f}_preempted_source_shadow = source` immediately before each overwrite (both blend paths). The `_shadow` suffix is deliberate — it rides `forecast_error_log.py`'s generic `{short}_*_shadow` pass-through into the pair log as `preempted_source_shadow`, avoiding a writer edit duplicated across the main and `wd` branches.
2. New `counterfactual_served_err(row, field)` walks the runtime source-depth chain (`_NBM_CHAIN` per field mirroring "deepest available NBM layer wins"; `_HRRR_CHAIN` otherwise). `score()` uses `row['error']` for shadow rows, counterfactual for applied rows. Pre-v0.7.21 applied rows have no stamp and are **dropped from the cell entirely** (not just from served_mae) so all four MAE series keep one population; count surfaces as `n_excluded_no_counterfactual`.

**Writeback allowlist completed** to `("nbm", "l1_blend", "nws", "blend")`. `nws` and `blend` were latent — `cleared_for_wire_nws: 0` with zero cell rows, `_BLENDER_APPLIED_FIELDS = frozenset()` — but both would have shipped the same scored-a-value-users-never-saw bug the moment a cell cleared. Guard added: `nws` is stamped as source even when `{f}_nws` was missing and the apply block fell through to HRRR, so rows whose `{f}_applied != "nws"` are skipped rather than re-rounded.

Full verifier re-run on live pair log: unchanged 9/10/1/0, no applied-cell note — correct, cached log predates this morning's applied rows and 24–47h leads haven't closed.

## Corrections I made to my own earlier calls this session

- Claimed v0.7.20 would be **inert** until nw_flow returned. It fired within 25 minutes. My "zero nw_flow hours" check read a per-hour regime key the snapshot doesn't carry, so an empty result looked like evidence when it was vacuous. **Count applied rows, don't infer from a regime field you haven't confirmed exists.**
- Called `wg/nw_flow/6-11h` ship-ready off the digest's one-line summary. The earning audit's halves columns say 50d **+8.75 / +2.04%** — second half under the +3% threshold, the exact reason v0.7.17 held it (+9.52/+2.11 then). Still fails. Read the audit's halves, not the digest summary line.

## Joe said he "added" the applicability registration — he had not

`collector.py` unmodified, no new commit, `l1_static_blend.describe_applicability` imported nowhere, live map still 20 layers. The descriptor I extended with `n_applied_cells`/`applied_cells` is still dead code. **Still open.**

## Open / not done

- **Verify the v0.7.21 provenance stamp + writeback on the next `nw_flow/24-47` hour** (see top — the only piece of the two ships not observed live).
- Applicability-map registration for the blender.
- `corrections_debug.html`: line 2320 still documents the superseded flip plan; Recent Activity still shows 09-29 as "today" (09-30, 10-01, 10-02 all missing).
- NBM skip pass: **3 ADDs** (wd/nor_easter/12-23, wd/nor_easter/24-47, wd/se_flow/24-47), **no REMOVE**. `wg/nor_easter/12-23` excluded — halves −0.00/−10.90, half A empty.
- Untriaged digest: h FRESH FIRE (3d +44.6% vs 7d +5.3%) + τ-suspect at 12-23h (+10.2% vs raw) — note the blender's cascade-bypass targets the same field/shape; `pp` ANOMALY worsening +124.8% → +177.7%; `pa` WATCH +556.2% with no explaining memory.

## Collector health

Post-v0.7.20 cold start 48.4 → 525.8 MiB (+477), matching the clean historical pattern (09-26: 48.7 → 465.7). Warm instances then climb ~+20 MiB/tick to 824; pre-deploy instances had reached 938. Known leak per [[project_collector_memory_leak_hunt]], not a v0.7.20 effect — the deploy reset the baseline.

## Related

- [[feedback_apply_flip_invalidates_shadow_verifier]] — new rule from this session.
- [[project_l1_static_blend_v076]] — updated with the partial-apply state.
- [[feedback_shadow_write_applied_layer_trap]] · [[feedback_selector_prod_vs_prod]] · [[feedback_shipped_flag_verify_effect]]
- [[project_10_01_session]] — prior session.
