---
name: project-09-08-late-evening-session
description: "Session narrative for 2026-09-08 late evening — third session of the day, driven by trust-check on scoreboard tiles. 2 ships (v0.6.569 attribution decomposition + Pipeline Lift per-field column + VC threshold retune; v0.6.570 debug page text sweep). Key reframe: metric independence paradigm formalized, additive-vs-quality-metric trade named."
metadata: 
  node_type: memory
  type: project
  originSessionId: f4f9924e-0098-4fb2-bee7-03e379adcce9
  modified: 2026-09-09T00:30:14.244Z
---

# 09-08 Tue late evening — attribution decomposition + metric-independence paradigm

**Session origin.** Third session of the day. Joe pinged with "back to scoreboard work" after this session had already logged the cc l3_nbm 24h REGRESS + sr.l5_nbm/sr.l3_nbm false-positive investigations ([[project_cc_l3_nbm_watch_09_08]], [[project_sr_l5_l3_nbm_sentry_false_positive_09_08]]). Then turned into a long thread about what the top-row tiles actually measure and what "independent measurement" requires.

## The metric-independence paradigm (formalized)

Joe: "I need to be able to separately measure everything. That's the only way this improves. The selector needs a score and it needs to be the right fucking score so that when we work to improve the score, we end up improving the thing we sought to improve. Same for pipeline lift, and overall lift."

**Rule:** each metric must isolate one layer's work such that improving the metric implies improving that layer specifically. No merging.

## Two failed attempts on my part before landing correct answer

1. **Attempt 1: "Pipeline Lift tile is merged with Total Lift"** — I read `analysis/scoreboard_v2.py:480`'s `pipeline_value_add_pp = best_mean_pct - prod_mean_pct` and concluded the tile duplicates Total Lift. Wrong: that field is dead code, not wired to any tile. Actual tile reads `per_field_scoring.py`'s `corr_vs_l1_pct` = `(l1_selected − prod) / l1_selected` via JS in `corrections_debug.html:4258`. Correct once I checked what the tile actually reads. **Lesson: [[feedback_verify_writers_for_read_paths]] applies to both directions — trace what the RENDER path actually reads, not what the JSON has.**

2. **Attempt 2: "Referee — cap Selector Skill by Total Lift"** — Joe caught this immediately: "you're being imprecise and it's pissing me off." Capping one metric by another merges them, destroying independence. Retracted before shipping. **Lesson: any proposed "consistency fix" that couples metrics violates the paradigm.**

## The actual finding — corr_vs_l1_pct collapses when selector picks user default

Joe screenshot of live tile: Total Lift 7d median +0.4% mean +4.4% · Pipeline Lift 7d median +0.4% mean +5.4%. Nearly identical. Joe: "Just a coincidence?"

**Not a coincidence.** For NBM-scope fields where selector picks NBM: `l1_selected = NBM raw = user default`, so `(l1_selected − prod) / l1_selected` = `(best_raw − prod) / best_raw` = Total Lift. For HRRR-only fields: selector always picks HRRR = user default, same collapse. The two metrics diverge only on rows where selector picks HRRR for an NBM-scope field (today: h, ws, ch). Aggregate is dominated by the NBM-picked majority so summary numbers look nearly identical.

This is a real property of the current selector regime, not a metric bug. But it means Pipeline Lift isn't doing independent work aggregate-wise.

## The additive-vs-quality trade — you can't have both

Three natural counterfactuals for the three layers:
- **Total Lift** counterfactual = user default (what user sees without our system)
- **Cascade** counterfactual = L1_selected (what would ship if selector picked this raw without cascade)
- **Selector** counterfactual = alternative pick (what would ship if we picked the other raw)

For additive decomposition, all three metrics must share one denominator. Forcing that means one layer gets attributed weirdly: if baseline = user default, then selector's default-confirmation work is worth exactly 0 by construction (selector picking user default adds nothing over the user's counterfactual). But that IS work the selector does — it's just invisible to a user-anchored additive framing.

**You cannot have (a) additive decomposition, (b) each layer credited for its own work, and (c) baseline that reflects the user's counterfactual — all three at once.**

## The ship — separate panels for separate questions

**v0.6.569 shipped both framings, cleanly separated:**

1. **Top-row quality tiles (existing):** Total Lift, Pipeline Lift (corr_vs_l1_pct), Selector Skill (VC). Each measures a layer against its NATURAL counterfactual. Non-additive by design. Retained unchanged; Pipeline Lift not deleted despite empirical duplication with Total Lift in the current selector regime, because it'll diverge when the selector picks HRRR more often.

2. **Attribution panels (new, subordinate row):** Total = Routing + Cascade, all three in pp of user default. Additive by construction (per-row). Mean panel = additive; median panel = per-column typical field, NOT additive (medians don't sum — different fields set each column's median). Median tile first (matches top-row median-first convention); mean tile wider for emphasis of the additive story.

## Live numbers on the shipped attribution panels (end of session)

**Mean panel (additive):**
- 7 Day: routing **−4.0%** + cascade **+8.4%** = total **+4.4%**
- 24 Hour: routing **−3.5%** + cascade **+17.1%** = total **+13.6%**

**Median panel (per-column, not additive):**
- 7 Day: routing +0.0% · cascade +0.8% · total +0.8%
- 24 Hour: routing +0.0% · cascade +7.6% · total +7.5%

**Big finding:** selector's routing contribution is NEGATIVE on both windows in mean. The cascade is doing all the work AND recovering the selector's losses. Median routing = 0 because most fields have selector picking user default → median lands on a zero row. Honest reflection of the current selector regime — selector isn't earning its keep right now; walker wire on 09-11+ should shift this.

## v0.6.569 also included

- **Per-field Pipeline Lift column** in the diagnostic table between Total Lift and HRRR Pipeline Skill. Displays existing corr_vs_l1_pct so the tile aggregate is auditable per field.
- **Selector Skill WFL threshold retune:** ≥+70% winning, ≤+30% losing (was ≥+33%/≤0%). Prior bar painted +48% VC green even though selector was leaving over half the oracle gap on the table. `_clsVC` tile classifier + WFL bands share the new scale.

## v0.6.570 — debug page text sweep

Joe asked to trim Recent Activity to 3 days + tighten What's running / Engineering updates language.

- Recent Activity: kept 09-08/09-07/09-06/09-05, dropped 09-04 through 08-31 + old trimmed-tail marker. Today's entry (was only morning ships) extended to include evening ships v0.6.564-569 + cc/sr investigations.
- **L4 scope stale in 3 places** — was `{ch, cc}`, should be `{ch}` since cc dropped HRRR L4 2026-08-28 v0.6.515 and NBM L4 2026-09-08 v0.6.563. Fixed in What's running + Engineering updates cc-row chain + Engineering updates L4 summary.
- **h row chain stale** — showed `L1 → L2 additive → L4 diurnal`; h has never been in HRRR L4_FIELDS. Fixed to `L1 → L2 additive`.
- **L3 row stale** — `{wg, ch, cm, pp}` → `{wg, ch, cm}` (pp dropped 2026-07-04 v0.6.304).
- **NBM cell-count references (3 places)** — hard-coded "10 cells: wg 12-47h, wd 12-23h..." was stale. Replaced with today's actual field-level picks (dp, wg, wd, cc, sr majority-NBM) + pointer to Total Lift tile for real-time picks so future drift doesn't recur.

## Retracted decisions

- **Aggregate opportunity-gap tile** (from morning session's open decisions #1) — RETRACTED. Redundant with Selector Skill VC: `100% − Selector Skill = aggregate opportunity gap`. Nothing to build.
- **Referee-cap Selector Skill by Total Lift** — RETRACTED same session as proposed. Would merge the metrics.
- **Two per-cascade top tiles (HRRR Cascade Skill + NBM Cascade Skill)** — CONSIDERED, not shipped. Per-field HRRR/NBM Pipe Skill columns already provide cascade attribution when needed to drill; adding two more top tiles would clutter. If needed later, medians of those columns give the numbers directly.

## Open decisions after tonight

1. **dp derivation override** — still parked to 09-11 wire. dp moved REGRESS → WATCH already before wire.
2. **VC n/a fields visibility** — UX polish (cl, cm, pr, cc, dp silently excluded from tile via NBM_SCOPE). Unchanged.
3. **Full What's improving / Post-ship watches sweep** — many closed items still in-line (07-xx dates). Deferred to tomorrow after digest per Joe. See v0.6.570 commit note for candidates: `wg residual persistence gate 07-27 flip HELD`, `Pre-frontal cloud widening blocked 08-05 to 08-15`, `dp depression nor_easter watch n=279`, `wg L3 08-11 investigation flag`.
4. **ADDED_LAYERS registry** — small ship candidate. Mirror of KILLED_LAYERS in `analysis/nbm_regression_sentry.py:77` for recently-added layers (would auto-suppress today's false-positive sr.l3_nbm/sr.l5_nbm class). Not urgent.

## Recommended session-start prompt for next session
> "Digest review + debug page cleanup pass. Yesterday shipped v0.6.569 (attribution decomposition) + v0.6.570 (text sweep). Deferred: prune the What's improving section of long-closed 07-xx items. Also check attribution mean routing — was negative on both windows last night; if still negative post-walker-wire on 09-11, real selector concern."

## Lessons captured

- **Trace what the render path actually reads.** [[feedback_verify_writers_for_read_paths]] applies bidirectionally — don't just check that the writer produces a field, check that the display code reads THAT field (not a similarly-named cousin). I burned 30 minutes proposing to fix Pipeline Lift based on a metric field that no tile reads.
- **Metric independence is a hard paradigm, not a preference.** Merging (referee caps, averaging cascades, sharing denominators across metrics with different natural counterfactuals) will keep looking tempting and will keep being wrong. When in doubt: does improving THIS number imply improving THIS specific layer? If not, it's merged.
- **Additive decomposition and quality-metric independence are mutually exclusive.** Different questions, different panels. When Joe asks for "how much did each layer contribute" (additive) and "how good is each layer at its job" (quality), that's two panels, not one metric that does both.
- **The additive attribution has a load-bearing blind spot** — selector's default-confirmation work = 0 by construction. Nearly-all-Cascade attribution in current regime is honest reading, not a bug. Ship the panel with that disclosure in the sub-text.
- **Ship one thing at a time, verify visually before pushing.** Localhost verification caught alignment issues twice (mean panel wrap, then description-height mismatch pushing numbers to different y positions across panels). Both fixed inline before push.

Related: [[project_09_08_evening_session]] (session 2) · [[project_09_08_session]] (session 1 — morning) · [[project_cc_l3_nbm_watch_09_08]] · [[project_sr_l5_l3_nbm_sentry_false_positive_09_08]] · [[feedback_verify_writers_for_read_paths]] · [[feedback_measure_before_concluding]].
