---
name: project-10-06-session
description: "10-06 session. No ships. Digest triage only, plus a debug page sweep (v0.7.26). Dug into the h/t layer-shape τ-suspect alerts and found selector anti-selection, not decay-τ. Answered Joe's raw-difficulty question (0.83 mean — weather genuinely easier this week). Ran the scheduled sr learned_gbm 7d check: 4/5 cells positive, nw_flow/24-47 negative at the min_n_test floor."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-06T16:00:00.000Z
---

# 10-06 session

No ships, no deploys. Digest triage + two investigations Joe asked for + the scheduled sr check +
a debug-page sweep (v0.7.26, committed `16728556`).

## Memory-system note

This session found `docs/memory/` (checked into git, read by every recent session per its commit
history) is substantially ahead of the separate CLI auto-memory snapshot at
`~/.claude/projects/-Users-josephselby-Documents-myweather/memory/`, which still read 10-03 state
(v0.7.23 "uncommitted") at session start. `docs/memory/` is the one to trust; treat the other as
stale unless it's been refreshed.

## Digest triage (09:07 run, 209/209 OK)

- SHIP-ELIGIBLE: none. Needs attention: none. New kills: none.
- **New top alerts:** `h/production` and `t/production` τ-suspect (see investigation below).
- `h_cc_sat_guard_stage0`: STAGE 0 PROMOTE again, +42.5% (was +42.0% on 10-05), 20/24 STABLE, same
  unstable set — second consecutive PROMOTE day toward the 7-day gate.
- `wg.l3_nbm` NBM sentry still HOT (+6.8%→−11.6%) — 09-14 precedent, no action.
- NBM skip-ADD "CONFIRMED" line still carries `wg/nor_easter/12-23` with halves −0.00/−10.90 —
  same degenerate half-A that got it dropped from the 10-05 batch. Not a real confirm.
- Pair-log WATCH: ch, pp, pr, wg, ws — untriaged, no explaining memory found.
- `walkforward_l3l4_validator`: still 1/7 days, 1 tool-group — not gate-cleared.
- chp v0.7.9 verify, the two TEMPORARY nor_easter re-reviews, L4 add dp/h: none due yet
  (~10-08/09, 10-13).

## h/t τ-suspect investigated: selector anti-selection, not decay-τ

Both alerts have the classic "helps 0-5h, hurts later band" shape the sentry calls τ-suspect
(h: helps 0-5h −37.2%, hurts 12-23h +16.2%; t: helps 0-5h −17.1%, hurts 6-11h +16.1%). Pulled the
pair log (7d) and compared, on the **same row population**, `error_l1` (raw), `error_l2` (what L2
alone would score on every row), and real production (`error_{applied_layer}`):

| field/band | raw | L2-on-every-row | production |
|---|---|---|---|
| h/12-23h (n≈1,920) | 4.97 | **4.50 (helps)** | 5.76 (+16% hurt) |
| t/6-11h (n≈958) | 1.67 | **1.63 (helps)** | 1.92 (+15% hurt) |

L2 itself is fine or helping at the band the sentry flags as hurt — there's no decay constant to
shorten. Splitting the served rows by `selector_mechanism`/`applied_layer` at h/12-23h:
`l2_nbm` (737 rows, 5.75), `l4` (706, 5.77), `l2` (481, 5.66) — every branch the selector actually
chose loses to the L2-for-every-row counterfactual. Same shape at t/6-11h (`l2`-applied 1.97,
`l1`-applied 1.93, `l2_nbm`-applied 1.84, all worse than 1.63).

**Conclusion (hypothesis, one day's window):** this is the selector choosing among
`l2_nbm`/`l4`/`l2`/`l1` in a way that underperforms committing to L2 uniformly at these two
(field, band) pairs — the same bug class the sentry's own code comment already documents from a
2026-09-08 `t` case (`build_executive_summary.py:1057-1065`), just a different mechanism (there,
L2 had fully decayed and something deeper drove the hurt; here, L2 hasn't decayed and is actually
winning, but the selector routes away from it anyway). Shortening τ or adding a lead-band SKIP —
the sentry's own suggested fix — would be the wrong lever. Not shipped: single 7-day window,
stability not checked day-by-day, may still be entangled with the receding h NBM break
([[project_10_03_session]]). New rule: [[feedback_tau_suspect_can_be_selector_artifact]].

**Next step, not done:** pull the selector's fit/criteria for `h@12-23h` and `t@6-11h` specifically
and find why it routes toward `l2_nbm`/`l4` there when L2 wins in aggregate.

## Raw-difficulty index (answered Joe's question: has the weather been easier?)

`analysis/output/mae_over_time.json` → `raw_difficulty_index`, mean ratio **0.83** — this week's
raw-model MAE ran ~17% below the trailing-90d per-field baseline (7d excluded from the reference).
Not uniform: `sr` 0.63, `h` 0.70, `ws` 0.79, `dp` 0.81, `ch` 0.78, `cm` 0.86, `t` 0.88, `wd` 0.92
all easier than normal; `cl` 1.08 and `pr` 1.08 slightly harder; `pa` 0.19 is a near-zero-MAE unit
artifact (0.005 vs 0.026), not meaningful on its own. Conclusion given to Joe: some of the recent
good scores is weather, not correction-stack improvement — real tool, [[project_raw_difficulty_index]],
first-run finding 08-04, this is the first time it's been re-pulled and reported since.

## sr learned_gbm 7d Value-Captured check (scheduled ~10-06, v0.7.15 post-ship watch)

Pulled the pair log, split the 5 covered cells by `selector_mechanism` (`learned_gbm` vs
`band_pool`, same cells — pool always picks `nbm` for sr so `band_pool` rows are the fail-safe
fallback when learned features were missing). Regime key is `state_fc.regime_synoptic` /
`state_obs.regime_synoptic`, NOT a top-level `regime` field — a flat `r.get("regime")` silently
returns None for every row and reads as "no data," same class of trap as the `lead_h` key mistake
from 10-03.

| cell | band_pool MAE | learned_gbm MAE | lift | n (learned) |
|---|---|---|---|---|
| nw_flow/12-23 | 40.17 | 15.43 | **+61.6%** | 119 |
| nw_flow/24-47 | 23.53 | 28.57 | **−21.4%** | 150 |
| se_flow/12-23 | 81.41 | 74.11 | +9.0% | 108 |
| se_flow/24-47 | 96.07 | 65.79 | +31.5% | 110 |
| sw_flow/6-11 | 37.15 | 25.71 | +30.8% | 78 |

4/5 positive. `nw_flow/24-47` is negative and its n (150) sits exactly at the curated table's
`min_n_test` floor — not a thin-sample fluke. One day's read; recorded on the debug page
(post-ship watch, v0.7.15 entry) with a recheck date of 10-07. If still negative tomorrow, the
cell should come off `l1_learned_selector_curated.json` and fall back to band_pool.

## Debug page sweep — v0.7.26

`make check-stale` was clean both before and after (no date/counter drift found mechanically).
Manual sweep: Recent Activity rotated (10-06 added as today, 10-05 → 1 day ago, 10-04 → 2 days ago,
10-03 trimmed to `display:none` — already fully recorded in the v0.7.23 changelog entry, no data
loss). Three findings above written into the page (post-ship watch v0.7.15 entry, the cc Stage 0
Upcoming row, and a new Upcoming row for the τ-suspect hypothesis) so they're not chat-only.
Version bump only, no code/data change. Committed `16728556`, pushed.

## NOT done / carry forward

1. **sr `nw_flow/24-47` recheck 10-07** — if still negative, drop the cell from the learned table.
2. **h/t τ-suspect — pull selector fit criteria** for the two flagged (field, band) pairs; find why
   it anti-selects away from L2.
3. Everything already carried from 10-05 and untouched today: v0.7.24 effect check, chp recheck
   ~10-08/09, the two TEMPORARY nor_easter re-reviews (10-13), L4 add dp/h (post-10-13 or 2nd tool),
   cc Stage 0 day 3+ (needs 7 total), applicability-map registration, `tests/test_layer_tuple_sanity.py`
   pre-existing failure, `pa` WATCH still unexplained.

## Related

- [[feedback_tau_suspect_can_be_selector_artifact]] — new rule from this session
- [[project_layer_shape_sentry]] · [[project_09_08_session]] (the precedent the sentry's code comment cites)
- [[project_raw_difficulty_index]] · [[project_10_05_session]] · [[project_10_03_session]]
- [[feedback_pair_log_error_field]] (regime key trap, same class as `lead_h` vs `lead_hours`)
