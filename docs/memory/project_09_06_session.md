---
name: 09-06-session
description: "2026-09-06 Sun session: 1 ship + 1 collector deploy + session-end sweep. v0.6.552 wired by-regime walker into L1 selector (regime × band routing overrides on top of band pool; passive today, first clear 09-14). Cell-level Value Captured audit reframed why 24h Selector Skill card reads -20%: transitional plumbing (sr/wind cells recently flipped NBM but 7d rows lack error_l3_nbm) + real ne_flow-outlier regime routing errors for dp/cc/wd/h — walker was built exactly for the latter. wd.l3_nbm sentry HOT triaged as near-zero-flip false positive (raw wd drift +31%, layer tracked); sentry flip clause needs min-magnitude gate — followup flagged, not shipped."
metadata: 
  node_type: memory
  type: project
  originSessionId: a354d28d-559a-4556-b3c3-b97c1d578ece
  modified: 2026-09-07T11:08:40.233Z
---

# 2026-09-06 Sun session

> **⚠ SCORING-BUG CORRECTION (added 2026-09-07):** the cell-VC audit in this memo ran against contaminated per_field_scoring output. `analysis/per_field_scoring.py:_selected_l1_error` was mis-attributing NBM-routed rows as `hrrr_fallback` whenever `error_l3_nbm` was absent — i.e. for every h/dp/ws row after the 09-05 v0.6.551 L3_NBM h kill. Fixed in v0.6.554 (commit `9adf2b4`, 09-06 15:10 EDT), but not deployed to the publisher CF until 09-07 10:58 UTC (12-day-stale image). Re-audit against clean data (this repo's scratchpad `selector_cell_audit.py`, 58,282 rows, 2026-09-07T11:15 UTC):
> - **Median 7d VC ≈ +47% (all fields positive, +40–72%)** — not -51%. The negative headline was scoring-bug artifact.
> - **"9 of top-20 worst = sr × hrrr_fallback"** was 100% artifact. Zero sr cells appear as hrrr_fallback on clean data.
> - **"dp 24-47 ne_flow VC -818%"** was artifact. Clean 24h shows dp 24-47 nw_flow at **+72.9% VC (nbm pick)**; ne_flow at that band doesn't reach top-25 worst.
> - **cc/wd/h ne_flow 6-23h** cells reproduce as real red on clean data (cc 12-23 ne_flow -145%, wd 12-23 ne_flow -84%, h 6-11 ne_flow -117%). Walker was correctly targeted at this pattern.
> - **New red cells surfaced by clean audit that the contaminated one masked:** dp 12-23 pre_frontal -201%, ws 24-47 sw_flow -219%, ws 6-11 ne_flow -169%, wg 0-5 pre_frontal -160%, t 6-11 nw_flow -106%. These are candidates the walker isn't currently flagging — consider next diagnostic pass.
> - **v0.6.552 wire is not retracted.** Walker's own daily-diagnostic 7-cell flag list (h ne_flow 12-23, ws calm 0-5/6-11/12-23, ws/ch nw_flow) is consistent with the clean-audit regime-outlier pattern. 09-07 → 09-14 accumulation runs on clean data going forward.
>
> Deploy-hygiene root cause: any commit touching `analysis/*.py` for a script in `publisher/main.py:41` PUBLISHERS list must be paired with `make deploy-publisher`. This wasn't enforced; per_field_scoring script fix went 12 days without reaching production. Followup: enforce in CLAUDE.md §8 deploy workflow or via git pre-push hook. [[feedback_verify_completeness_claims]] + [[feedback_deploy_sequence]].

1 ship + 1 collector deploy (rev `00552-vut` cold-start clean 11:17 UTC) + session-end debug page + memory sweep (v0.6.553).

## Ship

### v0.6.552 — wire by-regime walker into L1 selector

`pick_source(field, lead_h, regime=None)` in `weather_collector/processors/l1_selector.py` gained optional `regime` param. Loads `l1_selector_by_regime_walker.json` at module init; when a cell has `cleared_for_wire == True` AND `flipped_in_window == False`, routes NBM — takes precedence over the band-pool pick. `forecast_snapshot.py` passes `_wdp_state_fc_by_lead[i]` (fc-time regime for lead i) into the call. Wire contract matches the walker's docstring exactly.

**Passive today.** Walker suppressed until 2026-09-07 per its `NOT_BEFORE_DATE`; earliest 7/7 clear is 2026-09-14. `_REGIME_OVERRIDES` loads empty on v0.6.552 → selector behaves identically to v0.6.551. Shipping now so wiring is in place before any clears land.

**Deploy:** rev `00552-vut` active by 11:17 UTC; two consecutive runs clean (cold + warm), MEMPROBE 47.7→430.7 mib on cold, no import errors.

## Cell-level Value Captured audit

Drove the ship. User asked "what can we work on to make the selector better." I offered 4 options; user chose #4 (diagnostic first) before #1 (wire the walker). Audit answered the question — endorsed #1 as the right next lever, no mind-change.

**Scratchpad script:** `/private/tmp/.../scratchpad/selector_cell_audit.py` — for each (field, band, regime) cell, computes n_paired, hit_rate, chosen_prod_mae, alt_prod_mae, oracle_prod_mae, value_captured_pct, majority pick over the same pool `per_field_scoring.py` uses.

**Two distinct drivers of the -51% median 7d VC:**

1. **Transitional plumbing.** sr + wind cells that recency-override flipped to NBM this week still have mostly pre-flip rows in the 7d window with no `error_l3_nbm` stamped → `hrrr_fallback` pick, HRRR shipped where NBM would have won. 9 of the top-20 worst cells are `sr × hrrr_fallback` (sr 12-23 calm VC -310%, sr 0-5 ne_flow -247%, etc.). Evaporates as v0.6.549 stamps accumulate — no work needed.

2. **Real per-regime routing errors band pool cannot see.** `ne_flow` is the outlier regime across four fields:
   - dp 24-47 ne_flow (n=393, chosen=3.53, alt=1.49, VC **-818%**) — selector says NBM, HRRR wins big (Magnus rides on good HRRR h/t corrections)
   - dp 12-23 sw_flow (n=206, VC -315%)
   - cc 12-23 ne_flow (n=233, VC -150%) + cc 6-11 ne_flow (n=151, VC -64%)
   - wd 12-23 ne_flow (n=233, VC -55%)
   - h 6-11 ne_flow (n=124, VC -137%)

The by-regime walker (v0.6.534) was built for exactly (2). Positive-VC cells show the flip potential: wd × nw_flow 12-23 VC +82%, ch × sw_flow 24-47 VC +83%, cc × pre_frontal +63-71%.

## Diagnostic conversation — pipeline vs selector

Joe pushed back twice today, both times correctly:

**Push 1:** I called the 7d scoreboard regression "an old wound rolling off the window." Joe pointed at the 24h Selector Skill card at median -19.9%. That's four days after v0.6.540, not eight — my "wait" framing didn't apply to the 24h number. Retracted. 24h card is a live routing signal, not decay.

**Push 2:** I then over-committed to "kill L3_NBM for t/ws/dp" as same-medicine-as-yesterday. Joe pointed at the Accuracy scoreboard — HRRR Pipeline Skill +2.9%/+11.1% and NBM Pipeline Skill +4.8%/+10.0% (medians/means) both positive across every field. Both cascades are working. What's red is Hit Rate 47.5% and Value Captured -51.4% — pure selector metrics. Correct answer: selector issue, not pipeline. My "kill L3_NBM t/ws/dp" was wrong mechanism (L3_NBM barely runs on t/ws/dp, sentry columns THIN n=0-28). Retracted before shipping.

Lesson worth carrying: [[feedback_check_own_arithmetic]] — when I want to fit today's data into yesterday's narrative ("same disease"), read the actual scoreboard columns before committing. The two pipeline-skill columns and the two selector columns answer different questions; conflating them causes wrong-ship recommendations.

## Sentry triage — wd.l3_nbm HOT NOT disease

Sentry logged `wd.l3_nbm HOT ★` (n_sust=6,456 n_fresh=3,195, ΔMAE +44.9%, help_s +5.35% → help_f -0.18%, Δhelp +5.52pp).

Cell-level breakdown (scratchpad diagnostic on paired raw+l3_nbm rows, 7d sustained vs 3d fresh):
- **Raw wd MAE spiked +31% by itself** — nw_flow 24-47 raw +60% (n=478 fresh), pre_frontal 12-23 raw +75%, sw_flow 24-47 raw +121% (n=188), sea_breeze 24-47 raw +155%. Weather genuinely harder for wd right now.
- **L3_NBM tracked raw.** Paired-total: raw 47.52→62.43, l3 44.87→59.51. Δhelp on paired-total only **+0.88pp** (well below WATCH's 8pp).

Not disease. The sentry's HOT verdict comes from the `flipped_to_hurt = help_s > 0 AND help_f < 0` clause at `analysis/nbm_regression_sentry.py:220`. help_s=+5.35 crosses zero to help_f=-0.18 — but the move is only 5.5pp. Same class as the 09-04 raw-drift false positive: absolute-metric HOT on real weather drift.

**Followup flagged, NOT shipped:** the flip clause needs a min-magnitude gate (e.g., only fire flip HOT when |help_s| + |help_f| ≥ 3pp) so near-zero oscillations don't spuriously HOT. Same class as v0.6.548's marginal-help refactor. Scope creep to ship today — Joe agreed hold.

## Scoreboard snapshot at ship

7d value-add mean **+0.72%**, 6 REGRESS / 3 GOOD/STRONG / 2 WATCH (t/dp/h/ws/wg/sr red; wd/cc/cm/ch/cl green-ish). Ship gate router-scope **+39.7%** (was +48.4% 09-03, +50.4% 09-02) — continuing to erode as 30d anchor loses volume. Recency override count 11 flips, all HRRR→NBM, zero the other direction — v0.6.540 writeback aftershock still bleeding out.

24h: value-add mean -0.66%. h GOOD +22.2% (v0.6.546 override + v0.6.551 kill both paying out on 24h). ch GOOD +39% (chp_nbm kill paying out).

Sentry 3 HOT: h.l3_nbm and ch.chp_nbm both stale (killed 09-05, windows still carry pre-kill data — expected to clear by 09-08). wd.l3_nbm new HOT — triaged as false positive per above.

## Clock-watches advancing

- **L1 by-regime walker** — suppression ends 09-07 tomorrow, then day 1/7. Earliest wire clear **09-14**.
- **l4_nbm cc DROP** — scheduled 09-09 skip-table curation slot.
- **h.l3_nbm + ch.chp_nbm sentry HOT** — expected to clear ~09-08 as post-kill data fills the sustained window.
- **h_cc_blend Stage 1** — day 4/7 or 5/7 (holding).
- **NBM skip-table curation** — 09-09 (3 days).

## Followups queued (NOT shipping today)

- **Sentry flip clause min-magnitude gate** — file: `analysis/nbm_regression_sentry.py:220`. Add `abs(help_s_pct) + abs(help_f_pct) >= 3.0` guard on the flip-to-hurt clause so near-zero oscillations don't spuriously HOT. Same class as [[feedback_check_own_arithmetic]] + 09-04 marginal refactor.
- **24h Selector Skill will bleed** as post-v0.6.549 sr and post-v0.6.552 walker-armed cells accumulate. Re-check 09-13 pre-clear.

## Lessons

- **Answer the actual question, not yesterday's narrative.** Twice today I fit today's data into yesterday's story ("old wound", "same disease t/ws/dp"). Joe caught both. [[feedback_refresh_current_state_before_defending]] applies — read what the columns are actually measuring today before invoking yesterday's frame.
- **Diagnostic before ship pays** when audit could invalidate the assumed lever. Joe's #4-first ordering was correct — if the audit had shown routing was mostly transitional plumbing, wiring the walker would have been premature. It didn't; walker was still the right lever; ship followed with confidence.
- **Scope discipline held.** wd sentry triage produced a followup (min-magnitude flip gate) that I flagged but did not ship. [[feedback_stop_after_minimum_ship]].
