---
name: 09-07-session
description: "2026-09-07 Mon session: 5 ships (v0.6.554 publisher deploy → v0.6.558 sentry gate) + full scoring audit. Discovered publisher CF was pinned to 08-26 image (12-day stale), letting v0.6.554 scoring fix land in the repo without reaching production — Selector Skill tile flipped between red (publisher-served old code) and green (local digest overrode) every morning. Fixed deploy; then audited every scoring script end to end. Four semantic reframes shipped as a result: L1_selected walks to raw of picked source (L3_NBM moved to correction side), Selector tile primary = Hit Rate then refined to Win Rate (ties excluded), scoreboard_v2 baseline = user-default (matches per_field_scoring). Plus queued 09-06 sentry flip-clause gate."
metadata:
  node_type: memory
  type: project
  originSessionId: 39396d72-ba15-4563-b4ac-84d727899d4e
  modified: 2026-09-07T19:46:52.733Z
---

# 2026-09-07 Mon session

5 ships (v0.6.554 → v0.6.558) — all analysis-only, no collector deploy. Publisher CF redeployed four times (10:58, 11:50, 12:07, 12:20 UTC). Full scoring audit end to end.

## Root discovery — publisher CF was 12 days stale

Session opened on "the selector is still terrible" reading from the debug page tile. Traced through several wrong diagnostic paths (documented in Lessons below) before checking the actual state:

- **v0.6.554** committed 09-06 15:10 EDT with the scoring fix for `per_field_scoring.py:_selected_l1_error` (post-L3_NBM-kill NBM fallback walk).
- **Publisher CF last deployed 2026-08-26** — 12 days before that fix landed.
- Every hourly publisher tick since 09-06 15:10 EDT overwrote `gs://myweather-data/per_field_scoring.json` with the pre-fix output. Joe's morning digest at 06:24 EDT ran the fixed local code and overwrote back to green. Publisher clobbered at 07:00 EDT. Tile flipped red → green → red every hour.

**Fix:** `make deploy-publisher` at 10:58 UTC. New revision `myweather-publisher-00018-vam`. Verified via `date -u` + `gcloud functions logs read` + fetching GCS `generated_at` timestamp — publisher CF now writes fixed output at the top of every hour.

**Deploy-hygiene root cause:** any commit touching `analysis/*.py` for a script in `publisher/main.py:PUBLISHERS` list must be paired with `make deploy-publisher`. Not enforced today. Followup: CLAUDE.md §8 addition or git pre-push hook. Same class as [[feedback_verify_completeness_claims]].

## Ships

### v0.6.554 — publisher CF redeployment
Not a code change — the fix committed 09-06 finally reached production 12 days late. Also re-ran cell-VC audit on clean data to check whether the walker wire (v0.6.552 09-06) was informed by contaminated numbers. Result: walker cell list still defensible on clean data (`h ne_flow 12-23`, `ws calm 0-5/6-11/12-23`, `ws/ch nw_flow`); NOT retracted. See correction note added to `[[project_09_06_session]]`.

### v0.6.555 — L1_selected walks to raw of picked source + Selector tile primary swap
`analysis/per_field_scoring.py:_selected_l1_error` — NBM path simplified from `error_l3_nbm → error_raw_nbm` walk to just `error_raw_nbm`. L3_NBM was excluded from `corr_vs_l1_pct` credit under the old attribution ("NBM's product"), but L3_NBM is a Wyman Cove local bias table (`analysis/l3_nbm_fit.py` fits it from pair-log residuals). Belongs on the correction side, not the reference side.

Both cascades now symmetric: L1_selected = raw of picked source; every Wyman Cove layer above raw (L2_NBM/L3_NBM/L4_NBM/L5_NBM/L6_NBM/chp_nbm/wdp_nbm on NBM side; L2/L3/L4/L5/L6/chp/dpbp/wsbp/wdp/clp on HRRR side) counts as our correction stack. Tile description "Prod vs L1 selector's pick... on top of raw" is now honest.

Also swapped Selector Skill tile primary from `chooser_vs_prod_pct` (pooled MAE ratio, easily misread as per-row rate) to `hit_rate_pct` (per-row picker rate). Value Captured rendered as secondary line.

### v0.6.556 — Hit Rate → Win Rate (ties excluded)
`_new_bucket` splits `hits` into `wins` (chosen strictly < alt), `losses` (chosen strictly > alt), `ties` (chosen == alt). `win_rate_pct = 100 × wins / (wins + losses)`. Ties drop from denominator.

Why: ties don't test picker skill — the cascades happen to agree, the router earns nothing. A router that always picks HRRR gets 100% hit rate on any tied row. Pre-v0.6.556 counted ties as wins, inflating tile 15-30pp on tie-heavy fields (ws/sr/ch). Worst case: ch 24h `97.9% Hit Rate / -895% VC` — the near-perfect Hit Rate was 507 ties out of 563 rows; 12 non-tie losses were catastrophic. Win Rate = 78.6% (44/56) — honest about the small decisive sample.

Effect on 7d field numbers: ch 85%→51%, sr 75%→55%, wg 66%→66%, t 60%→58%, cc 55%→53%. Tile median ~66% → ~58%.

### v0.6.557 — scoreboard_v2 baseline reframed
`analysis/scoreboard_v2.py:_compute_field_cell` + per-cell `_accumulate` — `best_public` changed from `argmin(hrrr_raw, nbm_raw)` per field to user-default (NBM raw for NBM-scope, HRRR raw for HRRR-only). Matches `per_field_scoring.py`'s `best_raw` from v0.6.478 + [[feedback_baseline_is_user_default]].

Two files with two baselines feeding tiles side by side on the same page was the failure mode. Total Lift (per_field_scoring, user-default) and Health & Reliability (scoreboard_v2, argmin) graded the same pool with different verdicts. Argmin is strictly harder than user-default — Health systematically under-classified confidence.

Effect small: NBM raw was already argmin winner on most NBM-scope fields. 7d `value_add_mean` -0.88% → -0.65% (+0.23pp softer); 24h -5.47% → -5.05% (+0.42pp). One field shifted LOW→MED on 7d Health; one HIGH→MED on 24h. Winning green/amber/red unchanged. National Source tile unaffected (that IS argmin comparison, kept as-is).

### v0.6.558 — sentry flip-to-hurt clause min-magnitude gate
`analysis/nbm_regression_sentry.py:220` — the `flipped_to_hurt = help_s > 0 AND help_f < 0` clause now requires `abs(help_s) + abs(help_f) >= 3.0` (`MIN_FLIP_MAGNITUDE_PP`). Prevents near-zero oscillations from firing HOT.

Followup queued from 09-06 wd.l3_nbm false HOT (help +5.35% → -0.18%, 5.5pp move, raw wd was drifting +31% by itself). Same class as v0.6.548's marginal-help refactor. Verified rerun: wd.l3_nbm naturally CLEAN today; h.l3_nbm and ch.chp_nbm both still HOT with |sum| = 27.8pp and 111.5pp (way above floor).

## Full scoring audit findings

Audited per_field_scoring.py, scoreboard_v2.py, mae_over_time.py, h_persistence_skill.py, pp_brier_reliability.py, nbm_l2_delta_audit.py, gate_firing_rollup.py end to end.

### Fixed today (semantic reframes above)
- D: L3_NBM attribution (walk to raw)
- E: Selector Skill arithmetic vs description (Hit → Win Rate)
- F: Pipeline Lift "on top of raw" (walk to raw)
- A: scoreboard_v2 baseline (user-default)
- Four stale docstrings in per_field_scoring.py (header, _selected_l1_error inline, warmup_note, HRRR-side counterfactual "deferred" comment moot since Lt retired 2 months ago)

### Deliberately not shipped
- **B: scoreboard_v2 has no current-config counterfactual** analogous to per_field_scoring's `total_current_config_pct`. Killed layers (L5_NBM sr, L6_NBM t scaffold) not skipped in scoreboard_v2's Prod MAE walk. Impact: for rolling-window retention period after any future kill, scoreboard_v2 rollup will lag the honest counterfactual. Kept as low-priority followup.
- **G: 7d window has no fossil-row gate for cascade changes** other than kills. Any cascade change (kill, add, selector-table refit) creates a ~7-day transient where 7d mixes pre- and post-change rows. Options considered: (a) do nothing, (b) tile annotation when recent change, (c) window clip. Joe chose (a) — kills are already handled by v0.6.494 counterfactual; adds and selector refits self-heal in a week; 24h stays honest throughout.

## "Was every reading between 8/28 and today bogus?"

Answer: no, but different metrics had different valid windows.

- **Hard-bogus 09-05 15:18 → 09-07 10:58 UTC (44h):** Selector Skill + Value Captured for h/dp/ws — L3_NBM h kill stopped stamping, scoring walked to hrrr_fallback and flipped chosen=NBM to chosen=HRRR in paired accounting. -90% / -211% / -114% false negatives.
- **Contaminated-input window pre-v0.6.540 (~08-19 to 09-02):** t/dp/ws/sr rows with selector=NBM had `applied_layer` mis-stamped as HRRR-side. Every metric on those rows measured wrong Prod. 7d windows through ~09-09 still contain some of those pre-fix rows.
- **Definitionally-different-but-honest:** Pipeline Lift pre-v0.6.555 under-attributed our stack (L3_NBM excluded); Hit Rate pre-v0.6.556 over-attributed (ties counted); Selector Skill was chooser_vs_prod magnitude (valid but easily misread); scoreboard_v2 argmin baseline (stricter than user-default but internally consistent).
- **Consistently honest throughout:** Total Lift for h/wg/wd/cc/ch/cl/cm; Accuracy scoreboard's HRRR/NBM Pipeline Skill columns; mae_over_time chart.

Practical: t/dp/ws/sr Selector/Pipeline decisions in the past week: contaminated. h Selector in the last 48h: contaminated. h Total Lift and wg/wd/cc/ch decisions: fine.

## Pipeline vs Selector "flip" from Aug 26

Joe's Aug 26 tile screenshot: Pipeline +2.2%/+12.6% (both green), Selector +6.2%/+12.0% (both green). Today: Pipeline +0.3%/+2.4% (Pipeline red for t/h/ws/sr), Selector Win Rate 57%/59% (all fields green). Apparent flip.

Real story: not just a metric artifact. Selector genuinely doing more work now (v0.6.546 recency overrides, v0.6.552 walker wire arming), routing more rows to NBM. NBM correction stack is shallower than HRRR (no dpbp/wsbp/clp equivalents). So router picks better AND local corrections apply less depth → tiles anti-correlate mechanistically. Same-metric apples-to-apples: chooser_vs_prod 7d Aug 26 +12% mean → today +21% mean (router genuinely improved). Pipeline Lift genuinely down: NBM stack is thinner.

Compounded by 09-05 kills (removed L3_NBM h + chp_nbm ch layer depth on those cells) and v0.6.540 09-02 writeback fix (pre-fix corr numbers inflated by HRRR-side mis-attribution — post-fix corr is honest).

Net Total Lift 7d: +0.3% median / +0.7% mean. Modestly positive, still beating user default. If we want Pipeline Lift side to catch up: build NBM-side specialists (chp_nbm replacement post-kill, dpbp_nbm, wsbp_nbm). Workstream, not a same-day fix.

## Clock-watches advancing

- **09-08 sentry check** — h.l3_nbm + ch.chp_nbm expected to clear as pre-kill sustained-window data ages out
- **09-09** — NBM skip-table curation ([[l4-nbm-cc-drop-prep]] recommendation stands)
- **09-14** — earliest by-regime walker clear (walker suppression ended 09-07, day 1/7 today)

## Followups queued

- **Deploy-hygiene enforcement:** CLAUDE.md §8 addition or git pre-push hook ensuring `make deploy-publisher` fires when `analysis/*.py` files in the PUBLISHERS list change. Root cause of today's 12-day silent scoring bug.
- **B (scoreboard_v2 current-config counterfactual):** copy `_DISABLED_LAYER_KEYS` pattern from per_field_scoring. Low priority.
- **NBM-side specialists workstream:** chp_nbm replacement, dpbp_nbm, wsbp_nbm equivalents. Would raise Pipeline Lift on NBM-routed rows.

## Lessons

- **Read the git log commit messages before diagnosing.** The v0.6.554 commit message literally said "per_field_scoring `_selected_l1_error` NBM fallback — Selector Skill card was mislabeling picks post-L3_NBM kills." Every wrong turn today was one `git log --oneline -5` away from being avoided. Applied [[feedback_check_own_arithmetic]] in the metric-semantics domain: check what the metric actually measures before diagnosing what the number means.
- **Metric semantics are three-way responsibility.** The code computes something. The tile description promises something else. The user reads it as a third thing. All three must align. Today's "Selector Skill" tile had all three mismatched (code = pooled magnitude ratio, description = per-row rate, user reading = something like hit rate). E and the Win Rate refinement were the fix. Same class: never trust a metric name to describe what the metric computes.
- **Deploy is part of shipping.** A commit that changes analysis code is not shipped until the CF runs it. 12 days between fix commit and production landing. Same class as [[feedback_deploy_sequence]].
- **Ties count for nothing.** Any per-row skill metric that counts ties as wins will inflate on tie-heavy fields and hide catastrophic magnitude losses on transition rows. The 24h ch case (97.9% Hit Rate / -895% VC) is the canonical demonstration.
- **When Joe pushes back on a metric reading, HE IS RIGHT MORE OFTEN THAN YOU ARE.** Four times today Joe corrected metric-semantics conflations before I ran the actual code. Each time I was wrong. [[feedback_refresh_current_state_before_defending]] and [[feedback_check_own_arithmetic]] both apply. Related to today: "fireable" moment when the git-log commit message was unread despite being in the session-start context.

Related: [[project_09_06_session]] · [[project_09_05_session]] · [[project_09_04_session]] · [[feedback_selector_prod_vs_prod]] · [[feedback_baseline_is_user_default]] · [[feedback_check_own_arithmetic]] · [[feedback_deploy_sequence]] · [[feedback_verify_completeness_claims]].
