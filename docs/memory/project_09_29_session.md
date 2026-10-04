---
name: project-09-29-session
description: "7 ships (v0.7.10 debug + h_cc_derivation · v0.7.11 TEMPORARY sr×nor_easter L3 bypass · v0.7.12 narrative refresh · v0.7.13 operator structural cleanup · v0.7.14 selector-terminology · v0.7.15 sr learned_gbm 5 cells finally live · v0.7.16 v5 schema fix + debug sweep). 2 collector deploys (v0.7.11 13:10 UTC, v0.7.15 15:50 UTC). Big finding: v0.7.5 pivot's sr side had shipped as a silent no-op for 3 days due to empty JSON + band-suffix schema mismatch — fixed. Wd dig: cascade-driven 7d loss (routing 0%, cascade -2.67%), L3_nbm sentry WATCH on wd; same circuit-breaker pattern as sr today but smaller (Δ +12.8pp vs sr's +54.8pp) and WATCH not HOT — held for sr-verify data. Nor_easter regime (since ~09-26) systemically degrading L3_nbm on multiple fields (sr, wd), NWS 3-way dp cells, static blender coverage."
metadata: 
  node_type: memory
  type: project
  originSessionId: 393ff97d-5dfc-493b-a2fb-a7e2f400b4b7
  modified: 2026-09-29T22:38:32.093Z
---

# 2026-09-29 Tuesday session — 7 ships (v0.7.10 through v0.7.16)

## Ships (all committed + pushed)

**Commit 65afba89 — v0.7.16 (no runtime change):**
- **`analysis/l1_selector_per_obs_classifier_stage1_v5.py` candidate writer fix.** One-line strip of `"h"` suffix from band values before serialization. `BANDS` tuple still uses `"12-23h"` for display; the JSON writer emits `"12-23"` to match runtime `_band_for_lead()` canonical form. Prevents recurrence of the silent-no-op bug that hid v0.7.5's sr side for 3 days on future ships from this pipeline. Also present unfixed in v2/v3/v4/plain stage1 scripts — they don't emit candidate JSONs today, so not swept, but same trap if repurposed.
- Debug page sweep: today's Recent Activity entry expanded to all 7 ships (was 3); Post-ship watches gained v0.7.13/14/15/16 entries.
- Wd dig documented (details in "Wd dig — held" section below).

**Commit 1a204c3e — v0.7.15 (Joe deployed 15:50 UTC, first ticks clean):**
- **`weather_collector/data/l1_learned_selector_curated.json`** populated with 5 sr STABLE GBM cells (`nw_flow/12-23`, `nw_flow/24-47`, `se_flow/12-23`, `se_flow/24-47`, `sw_flow/6-11`).
- Completes the sr side of the v0.7.5 router-as-authority pivot that had shipped 3 days ago as a **silent no-op**: `LEARNED_SELECTOR_SHADOW_ENABLED = True` was set, but the shipped curated JSON was empty, so the sr learned path never fired.
- Re-verified halves-stable on current pair-log (including 4 days of nor'easter data): A/B lifts +14 to +37% across the 5 cells.
- **Fixed a real schema bug caught while shipping.** The v5 candidate JSON used band `"0-5h"` / `"6-11h"` / `"12-23h"` / `"24-47h"` (with `h` suffix), but the runtime's `_band_for_lead()` returns bands without the suffix. Cell keys would never have matched. Stripped the `h` suffix in the shipped JSON. This is likely why the file was left empty — an earlier ship attempt would have looked live (loader silent, no errors) but never fired, so was reverted.
- ch cells from v5 candidate NOT shipped — already covered by `ims_threshold` per the v0.7.5 non-overlapping-mechanism split.
- Rollback: `cp weather_collector/data/l1_learned_selector_curated.json.pre-v0.7.15.bak` back over the shipped file (backup on disk, gitignored).
- Deploy 15:50:09 UTC (DEPLOYMENT_ROLLOUT). First 3 ticks (15:57, 16:07, 16:17) all clean — zero `l1_learned_selector: gbm shape mismatch` warnings = 5 cells loaded correctly. Pair-log verification of `selector_mechanism=learned_gbm` firing pending overnight (6-47h backstamp lag on covered leads).

**Commit e6539c06 — v0.7.14 (terminology consistency, no runtime):**
- **Naming rule established:** "selector" is the primary name for the layer. Applies to prose, section headings, narrative. Kept as-is: `l1_selector.py`, `pick_source()`, `selector_source` / `selector_mechanism` pair-log fields, "Selector Skill" UI card (code-tied). "Router-as-authority" retained only as the name of the v0.7.5 pivot's framing.
- **Why not "router":** the debug archive has a v0.6.432 "L1 router" that was retired 08-19 v0.6.437 and explicitly *replaced by the selector*. Calling the current layer "router" in new prose would collide with that archive entry. Prose consistency beats mechanical accuracy of the name.
- Swept only today's authored prose (v0.7.10-v0.7.13 memory + CHANGELOG + debug edits). Historical entries left untouched.

**Commit db4e1aca — v0.7.13 (operator narrative structural cleanup, no runtime):**
- **22 old post-ship watches archived** (all opened 08-30 through 09-15, all watch windows ≥14 days concluded). Set `display:none` on each `<li>`. Entries stay in source for audit; `CLOSED CLEAN` summary line below expanded to catalog every archived entry by ship-tag and date.
- Active post-ship watches now reads top-down as recent ships only: v0.7.10 through v0.7.12 + sr regression + 4 long-standing state flags (Lc, wsbp, l6_fix_b_refit, wg persistence-skill).
- **Today's Recent Activity entry compressed** from ~5,000 chars of session prose to ~1,700 chars of landmark summary. Discipline: Recent Activity is a scoreboard pointer, not a session doc.

**Commit e571f9c5 — v0.7.12 (debug narrative refresh, no runtime):**
- Humidity row narrative rewritten event-based (no drifting numbers). Two NBM cascade "which side wins" summaries at lines 2213 and 2250 replaced with pointers to live National Source tile + per-field Selector column. Skip-table cell count updated 15 → 17 (v0.7.11 +2).
- Added `cm dropped 09-15 v0.6.625` to the L3_NBM cascade history sentence (was stale).

**Commit 5c25263b — v0.7.11 (Joe deployed 13:10 UTC, first ticks clean):**
- **`weather_collector/data/skip_table_nbm_curated.json`** — added `sr × nor_easter × 12-23h` and `24-47h` to `l3_nbm` block. Runtime picks up via existing `skip_table_nbm.should_skip()` (field-agnostic dict lookup — no code change). Note+history record 2026-10-13 re-review date. Reversal = delete the two entries.
- **`analysis/l1_static_blend_shadow_verify.py`** — reconciled report totals per ChatGPT catch. Was labeling `2/13/7/7 of 20 curated cells` (sums to 29). Now splits into `curated (n=20: 2/7/4/7)` + `off-curated stamped (n=9: 0/6/3/0)`.
- Debug page: 6 expired September dates pruned from Upcoming; L3_FIELDS list corrected to drop cm (was stale post-v0.6.625); cm architecture row L3 struck-through; PBL gate "4-7d" → "rolling".
- Deploy verified 13:10:19 UTC (DEPLOYMENT_ROLLOUT), first two ticks (13:17, 13:18) clean. Pair-log verification pending overnight — 12-23h leads won't backstamp until obs at valid_time land in ~12+h.

**Commit 94ba039b — v0.7.10 (frontend-only, no deploy):**
- Debug page 09-29 sweep (Recent Activity + Upcoming + Post-ship watches + L1 blender tile).
- `analysis/h_cc_derivation.py` — one-line format guard for `pct()=None` crash on all-clear days (prod_cc MAE = 0 → `>+12.2f` blew up). Two call sites now print `n/a`.

**Commit d8d12814** — precursor debug page + h_cc_derivation edits (missed the version bump; caught by v0.7.10 catchup).

## Real finding — fresh-fire vs circuit-breaker frame distinction (from ChatGPT review)

Applied `feedback_fresh_fire_lucky_baseline_artifact` discipline to sr in the morning. **Wrong frame.** ChatGPT reframed correctly:

- **Fresh-fire lucky-baseline** = one-anomaly-day sentry with tiny denominators. Today's cc: 3d n=384 dominated by 09-26 all-clear day (raw MAE 1.77 vs typical 30-60). No action, waits out the window.
- **Circuit-breaker** = mechanism-verified loss on a real sample. Today's sr × nor_easter: known layer (l3_nbm), known regime (nor_easter), known direction (raw+L2 clean, L3 corrupts), two consecutive days worsening (Δ +7.6pp on 09-28 → Δ +54.8pp on 09-29), sample grown 39→220. Ship now, don't wait on 14d+50d.

The 14d+50d two-window gate cannot promptly validate a brand-new regime. Nor'easter started ~09-26; 50d accumulation is weeks away. Meanwhile the correction is degrading a source that's already good before it gets applied.

**Precedent for the emergency add:** v0.6.622 wd.se_flow/0-5h — same shape, regime-specific L3 loss, ship-first-verify-later.

## v0.7.8 verify — partial pass, not full pass

Ran `analysis/l1_static_blend_shadow_verify.py` post-fix. Off-curated stamp ratio dropped **84% → 41%**. Residual 1,126 rows is almost entirely `nor_easter` (629 dp + 471 h across 3 leads each) — a regime not in the curated table at all. Non-nor_easter off-curated: 26 rows. Fix confirmed working; residual is curation gap, not plumbing bug.

Also picked up **2 SHIP-READY cells** (up from 0 on 09-28):
- `h/nw_flow/24-47` +39.4% n=336, halves +38.9/+39.8
- `dp/nw_flow/24-47` +8.6% n=336, halves +9.3/+5.6

Both below curation gate `min_n_rows=400` AND most of the 7d window predates v0.7.8's clean-plumbing (~1 day of clean data). **Held on narrow flip.** Wait ~3 days for n≥400 halves-stable on strictly post-v0.7.8 rows, then decide (~10-02).

## l1_selector_fit_3way [promote→hold] — regime signal decay, NOT bug

Digest verdict flipped from "4 NWS-wire cells cleared" to "0 cleared". Compared old committed report vs today's — all 5 previously-cleared dp cells have **collapsed h2 (recent chronological half)**:

```
dp/nw_flow/0-5      h1/h2: +11.9/+29.7  →  +28.1/-16.8   UNSTABLE
dp/sw_flow/24-47    h1/h2:  +5.3/+13.2  →  +15.0/-59.1   not-optimal
dp/pre_frontal/12-23 h1/h2: +27.5/+19.9  →  +20.6/-21.0   not-optimal
dp/nw_flow/12-23    h1/h2: +12.8/+35.7  →  +34.7/ -2.2   UNSTABLE
dp/nw_flow/24-47    h1/h2: +10.9/+15.2  →  +15.5/ +1.6   UNSTABLE
```

Every h1 (older half) still positive; every h2 (recent half) collapsed. Sample DOUBLED (113k → 269k rows over 30d) — not a size story. **Root cause: nor_easter degrading NWS dp forecasts relative to NBM.** Walker gate caught the regression correctly. No action — do not ship, do not investigate deeper. If nor_easter fades and h2 recovers, walker re-clears naturally.

## Nor_easter static-blend fit (scratchpad) — universal ω schema doesn't fit

Tested whether nor_easter should be added to `l1_static_blend_curated.json`. Filtered pair-log to h+dp rows with `state_fc.regime_synoptic == nor_easter` + both `forecast_l1` and `forecast_raw_nbm` present (n=2,042 across 8 cells). Swept ω ∈ [0, 1] step 0.05.

Result: **0 SHIP-READY**. All cells THIN (n<400 gate; largest n=381 for h/12-23 and dp/12-23).

Key finding: **nor_easter's best-ω is HRRR-favoring** (dp best-ω=1.00 pure HRRR, h best-ω=0.65 HRRR-lean), while universal ω for h=0.44 / dp=0.27 both weight NBM higher. Scoring nor_easter with universal ω gives −13% to −152% lift.

**Design implication: the "universal ω per field" architecture doesn't fit nor_easter.** Would need per-regime ω schema extension (`regime_overrides` map) if we want to cover it. Held on schema change until at least one cell (h/12-23 most likely) clears n=400 halves-stable (~10-04).

## v0.7.15 pivot completion — sr GBM finally live after 3-day silent no-op

v0.7.5 (09-26) pitched "sr via `learned_gbm` + ch via `ims_threshold`." Ch shipped and has been running. Sr was set live via `LEARNED_SELECTOR_SHADOW_ENABLED = True` but **`l1_learned_selector_curated.json` was shipped with 0 cells**. The sr learned path never fired for 3 days. The 09-28 dig noted "zero learned_gbm rows" but framed it as "v0.7.5 verdict scope narrowed to ch-only" — the actual gap (the curated JSON is empty) was not called out until today.

Fixed by:
1. Re-running `analysis/l1_selector_per_obs_classifier_stage1_v5.py` on current pair-log → same 5 sr STABLE cells held halves-stable including 4 days of nor'easter data
2. Copying the v5 candidate JSON into the shipped path, **stripping the `h` band suffix** (candidate had `"12-23h"`, runtime `_band_for_lead()` returns `"12-23"` — cells would never have keyed correctly)
3. Deployed clean, 3 ticks with zero shape-mismatch warnings

**Root-cause hypothesis on why the file was empty:** an earlier ship almost certainly copied the v5 candidate over as-is, saw "no visible effect" (because the band suffix broke the key lookup), and reverted to empty rather than debug. The "shipped as no-op" state was silent because:
- The loader logs no warnings for a file with 0 cells (that's a valid state)
- The `LEARNED_SELECTOR_SHADOW_ENABLED = True` flag was true — nothing to alert on
- Digest verdicts on the fitter were positive (5 STABLE cells) — the analysis said "ready to ship"
- Only mechanism-attribution (v0.7.7) exposed the gap on 09-28 — and even then, framed as "narrow scope" rather than "shipped as no-op"

See [[feedback_shipped_flag_verify_effect]] for the pattern.

## Wd dig — held on ship (revisit tomorrow with sr-verify data)

Late-session dig on wd, the only formally-losing 7d field per ChatGPT read. Full attribution via v0.6.630 decomposition on `per_field_scoring.json`:

**7d:** Total Lift −2.67% = **routing 0.0% + cascade −2.67%.** Selector is fine (l1_selected_mae ≡ nbm_raw_mae = 22.069, 100% NBM picks; no routing loss because NBM raw is genuinely the best). Cascade is degrading raw NBM: NBM Pipeline Skill −2.49%.

**Which layer?** From this morning's digest: `wd.l3_nbm WATCH — layer help -3.4% → -16.1% (Δ +12.8pp)`. L3_nbm on wd is net-negative sustained AND worsening fresh.

**Which cells (FRESH, not yet CONFIRMED — 14d+50d gate not cleared):**
- `l3_nbm wd nor_easter 12-23h` n=228 lift −24.7%
- `l3_nbm wd nor_easter 24-47h` n=206 lift −17.7%
- `l3_nbm wd se_flow 24-47h` n=2,318 lift −8.9% (halves 50d +0.2/−7.6, unstable)
- `l3_nbm wd pre_frontal 24-47h` n=2,258 lift −3.9%
- + 4 smaller cells

Nor_easter/wd/12-23h and /24-47h fit the exact same circuit-breaker pattern as sr today (known layer/regime/direction, n above threshold, worsening).

**Held ship because:**
1. **Magnitude difference is real.** Sr was collapsing (Δ +54.8pp, sentry HOT). Wd is degrading (Δ +12.8pp, sentry WATCH — just below HOT threshold).
2. **v0.7.11 sr ship not yet validated.** If sr recovers overnight per plan, ship wd tomorrow as parallel. If sr doesn't recover, understand why before doing it again.
3. **Nor_easter L3 problem may be broader than per-cell bypasses.** If regime persists another week and L3 keeps losing on multiple regimes for wd, a wd × L3_nbm drop (parallel to h drop in v0.6.551) becomes more attractive than a growing list of temporary bypasses.
4. **Ship discipline.** 7 ships today. Another without evidence is reaching.

**Tomorrow decision:** if v0.7.11 sr shows `applied_layer=l2_nbm` firing cleanly + sentry cooled, wd × nor_easter × 12-23h + 24-47h L3 bypass is a 10-min ship (JSON edit + deploy). If sr shows something unexpected, learn from that first.

## Nor_easter contamination is systemic today

Nor_easter regime started ~09-26 and is now visibly breaking pre-existing selector cells across multiple analyzers:
- **l1_selector_fit_3way** (5 NWS-wire dp cells): all 5 lost their h2 (recent half) today; walker flipped promote→hold. Correct behavior.
- **sr × L3_nbm/nor_easter** (v0.7.11): shipped a per-cell bypass to stop the L3 correction from corrupting good raw+L2 solar on this regime.
- **v0.7.6 static blender curated cells**: 41% of shadow stamps landing on nor_easter (a regime not in the curated table). Not a bug — curation gap.
- **Nor_easter static-blend fit** (scratchpad): best-ω is HRRR-favoring (dp=1.00 pure HRRR, h=0.65), fundamentally different from the universal ω schema (h=0.44, dp=0.27). Won't fit until schema is extended.

**Rule of thumb:** whenever a mechanism starts flipping/degrading in a single week, check whether a new regime just showed up before touching the mechanism. Regime shift breaks fits before it breaks the analyzer.

## Session lessons

1. **Shipping a flag ≠ shipping an effect.** v0.7.5 flipped `LEARNED_SELECTOR_SHADOW_ENABLED = True` on 09-26. The effect didn't materialize until today's v0.7.15 because the curated cells JSON was empty AND the candidate JSON had a schema mismatch. Verify the effect fires on real data before declaring a ship done. See [[feedback_shipped_flag_verify_effect]].
2. **Fresh-fire vs circuit-breaker are two different frames** — easy to conflate. Fresh-fire = one-anomaly-day + tiny baseline. Circuit-breaker = mechanism-verified + n above threshold + two-day worsening. Ship the second, wait out the first. See [[feedback_fresh_fire_vs_circuit_breaker_frames]].
3. **Verdict flips on multi-day analyzers can be real regime signal, not bugs.** Compare old vs new halves before diving into script diffs. Today's l1_selector_fit_3way flip was the walker doing its job on nor_easter contamination.
4. **"Universal ω per field" is a strong architectural bet, but new regimes can violate the universal assumption.** Check sign of best-ω before adding cells to a universal-ω table.
5. **External review is worth reading.** ChatGPT caught two things today — the fresh-fire framing on sr, and the arithmetic error on verdict totals (2+13+7+7≠20). A third external observation (pipelines-good-selector-bad) reframed what "our week has been" — I'd been talking about the selector as if it were stable and boring, while every version bump since v0.7.0 has been selector work. Read reviewers seriously; correct fast; hold position only when you have one.
6. **Terminology drift** — this session accidentally re-introduced "router" alongside "selector" in prose. Reverted in v0.7.14. Rule going forward: "selector" for prose, code-tied entities keep their existing names. [[feedback_selector_is_primary_name]].
7. **CLAUDE.md rule 7 — bump version before every commit.** Missed it on d8d12814 (debug-only), had to catch up in v0.7.10. Second time in a week. Watch this on every commit.

## Non-goals held

- Did NOT ship narrow v0.7.6 apply-flip for nw_flow/24-47 (n=336 < 400 gate + clean-plumbing window too short).
- Did NOT add nor_easter cells to `l1_static_blend_curated.json` with universal ω (would hurt −13 to −152%).
- Did NOT modify `l1_selector_fit_3way.py` in response to the flip (walker was correct).
- Did NOT ship h learned_gbm cells — today's v5 re-run showed 0 STABLE h cells (all UNSTABLE / one-window / MARGINAL on current data, likely nor'easter contamination).
- Did NOT redeploy publisher.

## Files touched

- **Runtime (deployed):** `weather_collector/data/skip_table_nbm_curated.json` (v0.7.11 sr entries), `weather_collector/data/l1_learned_selector_curated.json` (v0.7.15 sr GBM cells), `weather_collector/data/l1_learned_selector_curated.json.pre-v0.7.15.bak` (rollback, gitignored)
- **Analysis:** `analysis/l1_static_blend_shadow_verify.py` (curated/off-curated tally split), `analysis/h_cc_derivation.py` (pct=None format guards)
- **Debug page:** `corrections_debug.html` (Recent Activity + Upcoming pruning + L3_FIELDS + cm row + L1 blender tile + v0.7.8 post-ship watch + sr regression watch + 22 old post-ship watches archived + humidity narrative + NBM cascade summaries + terminology sweep)
- **Docs:** `docs/CHANGELOG.md` (v0.7.10 through v0.7.15 entries)
- `index.html` v0.7.9 → v0.7.10 → v0.7.11 → v0.7.12 → v0.7.13 → v0.7.14 → v0.7.15
- `version.json`, `sw.js` (build.py bumps)
- Scratchpad: `fit_nor_easter_static_blend.py`, staging area for v0.7.15 curated JSON

## Clock-watches after today

- **Overnight → 2026-09-30 AM:** Two verifies from overnight backstamps: (a) v0.7.11 sr × nor_easter L3 bypass — 12-23h and 24-47h rows should show `applied_layer=l2_nbm` (not `l3_nbm`) on nor_easter cells; `nbm_regression_sentry sr.l3_nbm` should drop out of HOT. (b) v0.7.15 sr `learned_gbm` firing — first post-deploy sr rows in the 5 covered cells (nw_flow/12-23, nw_flow/24-47, se_flow/12-23, se_flow/24-47, sw_flow/6-11) should stamp `selector_mechanism=learned_gbm` (was `band_pool` before ship).
- **2026-09-30 AM (conditional):** if sr verifies clean → ship wd × nor_easter × 12-23h + 24-47h L3 bypass (10-min JSON edit + deploy, same shape as v0.7.11). See "Wd dig — held" section above.
- **~2026-10-02:** v0.7.6 nw_flow/24-47 narrow-flip decision. Re-run shadow verify when h+dp cells cross n≥400 on strictly post-v0.7.8 rows.
- **Fri 2026-10-03:** v0.7.5 ch-only verdict (per-mechanism attribution via `selector_mechanism` stamp). v0.7.6 shadow retro re-run.
- **~2026-10-04:** nor_easter static-blend re-evaluation. Decide on per-regime ω schema.
- **Mon 2026-10-05:** v0.7.9 chp gate 7d verify.
- **~2026-10-06 (v0.7.15 + 7d):** sr Value Captured trend on 7d Selector Skill card — if trending positive, GBM is earning; if flat or negative on covered cells, refit needed.
- **Mon 2026-10-13:** v0.7.11 sr × nor_easter L3 bypass re-review. Either remove (regime faded, walkforward proposed cleanly) or keep (regime persists, formal skip).

## Related

- [[project_09_28_session]] — v0.7.8 + v0.7.9 ships; sr audit trigger cleared (framing was selector-not-cause, correct then; today added the layer-level bypass).
- [[project_l1_static_blend_v076]] — v0.7.6 shadow retro update: 2 SHIP-READY (up from 0), off-curated 84%→41%, nor_easter schema-incompatibility discovered.
- [[project_router_as_authority_pivot]] — v0.7.5 verdict scope unchanged (ch-only via ims_threshold).
- [[feedback_fresh_fire_lucky_baseline_artifact]] — today's cc case fits perfectly (3 all-clear days). Today's sr case does NOT fit — that's the new distinction.
- [[project_backstamp_stale_09_24]] — reminder: pair-log freshness discipline (filter by run_time to isolate post-deploy).
