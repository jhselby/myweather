---
name: 09-05-session
description: "2026-09-05 Sat session: 1 ship + 1 collector deploy. v0.6.551 killed L3_NBM h and chp_nbm ch — both sentry-HOT under marginal-help metric for 2nd day, per-cell breakdown showed systematic (not weather-mix) degradation. Same disease identified on t/ws/dp/sr — NBM corrections dragging NBM prod below NBM raw — but L3_NBM error columns still THIN for those fields so sentry can't diagnose yet. Diagnostic conversation reframed scoreboard column semantics: Selector Skill picks min-PROD (not min-raw); Total Lift baseline is NBM raw for NBM-scope fields (not min-raw). Value-Add negative means at least one of {routing stale, corrections regress on routed path, both stacks under water}."
metadata: 
  node_type: memory
  type: project
  originSessionId: 676db01f-14ec-4178-b5a3-ceccf80ed406
  modified: 2026-09-06T01:56:46.062Z
---

# 2026-09-05 Sat session

1 ship + 1 collector deploy (rev `00551-xob` verified clean). Session-end debug page sweep intentionally held — will sweep once h/ch Value-Add signal has rotated through pair log (~24-48h).

## Ship

### v0.6.551 — kill L3_NBM h and chp_nbm ch

Both cells sentry-HOT under the marginal-help metric ([[project_09_04_session]] shipped v0.6.548 sentry refactor) for the 2nd consecutive day. Per-cell breakdown (regime × band, n≥40 per window, in scratchpad `nbm_hot_cell_breakdown.py`) showed the regression is **systematic, not weather-mix artifact**:

- **h.l3_nbm**: 14 of 15 cells have help_fresh negative. Only 1 improver (se_flow 24-47 flipped from +8% to +42%). Pattern: L2_NBM MAE dropped a lot fresh (h got easier), L3_NBM MAE stayed flat or rose — the static bias-shift table kept applying when L2 was already close.
- **ch.chp_nbm**: only 4 cells cleared n floor (thin scope). ALL 4 (se_flow 12-23/6-11/24-47, pre_frontal 6-11) flipped help→hurt. Same story — L4_NBM input got easier, persistence-of-obs blend didn't track.

Yesterday's h.l3_nbm cell breakdown ("ne_flow 24-47 degrader offset by se_flow 24-47 improver = weather-mix artifact") **did not hold today** — the offsetting story broke, degradation spread across nearly every regime.

**Fix:** two module-level flags. `L3_NBM_FIELDS` in `weather_collector/processors/l3_nbm.py` no longer contains `"h"` (falls through to L2_NBM). `CHP_NBM_CH_KILL = True` const in `weather_collector/processors/forecast_snapshot.py` guards the chp_nbm fire block (falls through to L4_NBM, which reads sentry-CLEAN). Both reversible one-liners.

**Deploy:** `make deploy-collector` returned clean, revision `00551-xob` serving 100% traffic by ~15:00 EDT. All 4 subsequent runs same-instance, MEMPROBE 985 MiB steady, no `l3_nbm`/`chp_nbm` errors. Frontend commit `800b91e` pushed.

## Diagnostic conversation — scoreboard column semantics

Joe pushed back twice on my framing; both corrections landed and are worth carrying forward.

### Correction 1: Selector picks min-PROD, not min-raw

I initially framed h Value-Add loss as "selector picked HRRR when NBM raw was better." Wrong frame. Per `per_field_scoring.py:596`, Selector Skill via `value_captured_pct = (alt_prod − chosen_prod) / (alt_prod − oracle_prod)` where oracle is per-row **min-prod**. Selector's mandate is min-prod, not min-raw. Same lesson as [[feedback_selector_prod_vs_prod]].

### Correction 2: Total Lift baseline is NBM raw, not min(HRRR raw, NBM raw)

Per `per_field_scoring.py:522`, `best_raw = NBM (user default)` for any NBM-scope field. NBM raw is the baseline the user gets if we do nothing — [[feedback_baseline_is_user_default]] and 08-25 evening reframe. (Note: `scoreboard_v2.py:260` still uses `argmin(hrrr, nbm)`, but the debug page reads per_field_scoring, so Joe's Total Lift is vs NBM raw.)

### The corrected paradox and its resolution

If Selector correctly picks min-prod AND NBM Pipeline Skill positive (nbm_prod < nbm_raw) AND selector routes to NBM, then prod ≤ nbm_prod ≤ nbm_raw, so Total Lift ≥ 0. If Total Lift is negative, one leg broke. Three ways:

1. **Corrections regress on the routed path** — nbm_prod > nbm_raw on chosen rows. Fixable by killing/skipping the offending layer. This is today's h & ch story.
2. **Routing stale** — sel_n negative means selector picked wrong source on today's data. Fixable by tightening v0.6.546 recency-override thresholds (7d → 5d window, 200 → 100 n floor).
3. **Both stacks under water** — even min-prod > best-raw. Needs both fixes.

The per_field decomposition (`sel_h / sel_n / corr / total`) tells you which leg broke. Read that instead of the two headline component tiles. Positive Selector Skill + positive Pipeline Skill does NOT sum to positive Value-Add — those measure component quality, not user outcome.

## What's still red and why

**Live scoreboard 19:00 UTC (pre-deploy pair-log rotation):**
- 24h value-add mean **+0.95%** (up from morning -0.59%); 5 HIGH / 3 MED / 6 LOW health
- **Recovered:** h -21% → +4.0% GOOD (v0.6.546 recency override finally paying dividends). wg → flat.
- **Newly red:** t -17.1%, ws -19.6%, dp -18.1% — all REGRESS. Same pattern as h: NBM raw is much better than what prod delivered, but corrections on the routed path (per-band mix HRRR/NBM) dragged prod worse than NBM raw.

Sentry couldn't diagnose t/ws/dp/sr this morning because their L3_NBM error columns are still THIN (n_fresh=0 or 55) — cascade hasn't accumulated enough post-v0.6.540 (2026-09-02) writeback-fix rows yet. **Should populate over the next 2-3 days.** When they do, if sentry flags any as HOT, apply the same-class fix (kill or skip).

## Selector table snapshot (fitted 2026-09-05T11:04)

9 recency overrides active. Yesterday's `h 6-11` HRRR→NBM flip **reverted** today (recency signal collapsed). Currently overridden HRRR→NBM: `sr` all 4 bands, `t 12-23`, `t 24-47`, `h 12-23`, `wd 0-5`, `ws 24-47`. Anchor picks not overridden: `dp` 6-47h (30d NBM winner already), `wg` 6-47h, `cc` all, `ch` all (HRRR wins prod-vs-prod historically despite NBM raw being better — this is the tell that ch's NBM stack is regressing).

30d prod-vs-prod lift shows huge negatives across many bands (t 0-5 -193%, sr short-lead -100%+, ch 24-47 -70%), meaning NBM's correction stack has historically been dragging NBM prod well below HRRR prod. Recency overrides on newly-improved bands are the recovery mechanism. **If NBM corrections continue to net-hurt across fields, the whole "route to NBM" story is unstable and we should prune more layers.**

## Expected signal timeline for v0.6.551

- **Next 1-3h:** short-lead (0-5h) pair-log rows start closing under new config
- **Next 6-12h:** 6-11h and 12-23h bands populate
- **Next 24h:** 24-47h band fully rotated
- **Sun morning digest:** should show `h.l3_nbm` and `ch.chp_nbm` dropped from sentry HOT list (no more error_ column stamping); h `corr` should climb toward zero; ch `corr` already +39.5% so unlikely to move much

## Clock-watches advancing

- **wg residual persistence walker: day 6/7 → tomorrow is earliest wire**. But `ne_flow/24-47` added fresh today (16 cells vs 15 stable for prior 4 days) — 1 flip inside window. whitelist_streak SHADOW PASS min-J 0.833 but walker's own "consistent daily SHIP" gate reads 0 cells. **Recommendation:** don't ship on day 7 if today's fresh add repeats; wait for re-stabilized 7-day window per [[feedback_streak_walker_robustness]].
- **h_cc_blend Stage 1**: day 4/7 CHURN (pre_frontal set change). Clock resets on churn.
- **h/dp residual persistence walkers**: too messy to ship (h has 15 flips, dp has 4). Not close.
- **NBM skip-table curation**: still 09-09 (4 days). [[l4-nbm-cc-drop-prep]] recommendation stands.

## dp v0.6.540 warmup — Fri 09-05 trigger closed with caveat

Fri 09-05 read per [[project_dp_v0540_warmup_watch]]:
- Overall dp Total Lift: -15.6% (just inside [-20%, +15%] pass band) ✓
- 12-47h ≥ -30%: PASS (-26.1% and -24.2%)
- 0-5h positive: **FAIL** at -53.7% — HRRR raw 1.28 crushes NBM raw 2.63 on fresh 0-5h
- 6-11h ≈ -15% real-bug criterion: inconclusive (n=60 thin)

**But:** today's L1 fit auto-reverted the v0.6.546 dp 0-5 HRRR→NBM override (30d shows HRRR wins by 92%, recent didn't clear threshold). Recency-override system worked as designed. The 0-5h scoreboard read is pair-log-lag from yesterday's stamps. **Not a real bug — memo can be marked closed.**

## Lessons

- **Trust the user's system-level view.** Joe pushed back twice today (once on selector mandate, once on Total Lift baseline). Both corrections were right; both times my first framing was wrong in a way that would have led me down a bad diagnostic path. Apply [[feedback_check_own_arithmetic]] to metric semantics before diagnosing anything.
- **Per-cell breakdown catches the difference between weather-mix and systemic regression.** Yesterday's h.l3_nbm sentry HOT was called weather-mix on one degrader + one improver. Today the same script showed 14/15 cells degrading — systemic. Cell breakdown belongs in the sentry investigation kit whenever it fires 2+ days.
- **NBM cascade layers stamp error_{layer} keys before their scope goes live in the fresh sentry window.** t/ws/dp/sr have `error_l3_nbm` at n=0 or n=55 for fresh 3d despite v0.6.540 09-02 writeback fix. Their sentry diagnosis is still 2-3 days out. Watch, don't assume.

Related: [[project_09_04_session]] · [[project_09_03_session]] · [[project_dp_v0540_warmup_watch]] · [[project_selector_recency_override_watch]] · [[feedback_selector_prod_vs_prod]] · [[feedback_baseline_is_user_default]] · [[feedback_check_own_arithmetic]].
