---
name: project-09-08-evening-session
description: Session narrative for 2026-09-08 evening — trust-check conversation on scoreboard bouncing led to 3 ships (v0.6.566-568) around L1 by-regime walker gate loosening and Selector Skill tile Win Rate → Value Captured swap. 09-11 = first possible walker cell wire.
metadata: 
  node_type: memory
  type: project
  originSessionId: 8f88a24c-b23a-4ede-a471-f0f3685fbc5d
  modified: 2026-09-08T21:40:24.886Z
---

# 09-08 Tue evening — scoreboard trust-check + selector work

**Session origin.** Joe opened saying scoreboard has bounced a lot, he's lost trust and feels unanchored. Requested a fresh audit + conversation before any action. Correct triage: distinguish real predictive-quality changes from measurement-layer changes.

**5-day audit (v0.6.548 → v0.6.565):** 18 ships. Only 4 were real predictive changes (549 sr add, 551 h/ch kills, 552 walker wire, 563 cc drop). 4 were scoreboard-yardstick redefinitions (555/556/557/560). 4 were instrumentation-bug fixes (554/558/561/562). Rest were housekeeping. The bouncing was legit: routing genuinely changed (551, 552) + measure was redefined 4 times + sentry logic shipped false positives that needed papering over. See [[feedback_measure_before_concluding]] class — the tile was moving because we kept moving the tile.

## 3 ships this session

### v0.6.566 — L1 by-regime walker gate loosened
- `analysis/l1_selector_fit_by_regime.py`: diagnostic now emits per-cell `n_today` (24h rolling paired-sample count) alongside 30d rolling `n`.
- `analysis/l1_selector_fit_by_regime_walker.py`: `GATE_WINDOW_DAYS 7 → 3`, added `MIN_DAILY_N = 20` enforced on each day. History payload stores `n_today`; pre-change entries treated as 0 (fail-safe). Walker gate is `n_seen==3 AND n_pos==3 AND min(n_today across window) >= 20`.
- Runtime contract unchanged (`cleared_for_wire`, `flipped_in_window` names preserved) — collector's `l1_selector.py` needs no code change. Walker JSON deployed via `make deploy-collector` at 18:12 UTC. Verified via CF logs: fresh instance ran clean at 18:17.
- **Motivation:** 24h scoreboard shows regime flip (hrrr_raw beats nbm_raw by 30-40% on t/h) while selector still on 30d NBM fit. 7d gate held wire out to 09-14; 3-day + per-day n keeps "no chasing one noisy day" property while shortening horizon.
- **Earliest cell wire = 09-11.** Today = day 1 of new-format history. Need days 09-08, 09-09, 09-10 all present + all n_today ≥ 20. Walker clears on 09-10; selector fit picks it up nightly 09-10; routing goes live 09-11 collector runs. **No collector deploy needed at wire time — already done today.**
- **Cell to watch first:** `ws/nw_flow/12-23` — today's n_today=228, well above 20. If NW flow persists 3 days, first to clear.
- **Design note:** cells for rare regimes (ne_flow, calm) will take longer because n_today=0 when regime not active. Intended, not a bug.

### v0.6.567 — Selector Skill tile primary swapped Win Rate → Value Captured
- Joe pointed at tile: "Win Rate looks great, barely moves overall lift." Root cause: Win Rate counts each row equally regardless of magnitude of pick-vs-alternative gap. Can be 60% right by 0.1°F while losing 40% by 3°F.
- **Value Captured** = `(alt_prod_MAE - chosen_prod_MAE) / (alt_prod_MAE - oracle_prod_MAE)` — magnitude-aware, n-weighted, % of oracle. Already computed per-field in `per_field_scoring.py:596`; this ship promoted it to tile primary.
- **Range:** +100% = oracle, 0% = broke even, negative = anti-selection (unbounded low — see 09-07 ch 24h −895% as historical example when small denominator meets big negative numerator).
- Initially kept Win Rate as secondary; Joe questioned "why did you keep this?" — right question, I had no good answer beyond reflex.

### v0.6.568 — Trim Win Rate secondary + VC-tuned WFL thresholds
- Removed Win Rate secondary line entirely. Description trimmed to one sentence so tile height matches Total Lift + Pipeline Lift.
- **WFL thresholds tuned to metric:** ≥+33% winning, ≤0% losing, 0-33% flat (was shared ±2%). Big median/mean numbers use dedicated `_clsVC` classifier so tile paint + WFL agree.
- **Rationale for +33%:** captures at least a third of oracle routing gap = non-trivial work. Not so tight that a field going +55% → +45% during regime shift flips out of green. 0% is unambiguous (any positive = selector helping; any negative = anti-selection).
- **Effect:** ws honestly re-marked flat at +24% (was misleadingly "winning" under +2% bar). Other 6 NBM-scope fields stay green. 7d mean +50.5% median +51.3%.

## Scoreboard state at session end

| window | prod%hrrr | best_chosen%hrrr | pipeline_add_pp | REGRESS fields | GREEN fields |
|---|---|---|---|---|---|
| 7d  | 82.6 | 83.7 | +1.11 | t, dp, h, ws, sr | wg, wd, cc, cm, ch |
| 24h | 97.0 | 108.4 | +11.49 | dp, wg, pr | 8 others |

**Reading:** 7d looks bad but 4 of those days are pre-kill (v0.6.551 on 09-05). Will age out ~09-12. 24h is honest and shows the correction stack is fine post-kill. **The 7d "production trend is shit" reading is NOT a signal to act on — it's window contamination.** 24h is the live health measure right now.

**dp is the standout ongoing problem.** REGRESS in both windows (7d −13.79%, 24h −31.89%). dp is derived (Magnus from t+h), inherits t/h routing errors. Won't self-heal until t/h routing corrects. Expected to improve after 09-11 wire; if not, dp derivation override becomes the ship.

## Open decisions — did NOT act, left on table
1. **Aggregate opportunity-gap tile** — no rollup on debug page shows "how much routing lift are we currently leaving on the table." Had to dig into walker JSON to see it. Small build, real instrumentation gap. Would have flagged today's regime flip without conversation.
2. **dp temporary derivation override** — proposed forcing dp to derive from best_public_per_cell instead of L1_selected until routing settles. Held because 09-11 wire is close. Revisit if dp still REGRESS after 09-11.
3. **Value Captured n/a fields visibility** — cl, cm, pr, cc, dp all silently excluded from tile via NBM_SCOPE. Worth deciding if exclusion should be visible ("6 of 9 fields scored") or left silent.

## Recommended session-start prompt for next session
> "Continuing scoreboard work from 09-08 evening. Three ships pushed (v0.6.566-568). Key change: L1 by-regime walker gate 7d→3d + per-day n≥20 floor. Earliest cell wire = 09-11. First check today's walker output (`weather_collector/data/l1_selector_by_regime_walker.json` — look at `n_cells_cleared` and `per_cell` for cleared_for_wire), then current 24h scoreboard to see if routing corrected. dp still expected to regress until t/h routing catches up."

## Lessons captured
- **Rate metrics deceive when magnitudes are asymmetric.** Win Rate = fraction of times we were directionally right; Value Captured = fraction of magnitude we captured. When they disagree, magnitude wins for shipping decisions. Direction alone belongs in diagnostic tables, not top summary tiles. See [[feedback_scoreboard_vs_cell_aggregation]] class.
- **When the yardstick moves alongside the thing it measures, of course the reading jumps.** 5 days = 4 measure redefinitions + 2 real routing changes = user loses trust. If you must redefine a measure, ship a companion "compatibility" reading so the user can see what the old measure would say for a decay period.
- **A 30-day fit + 7-day recency + 7-day walker persistence = 3 layers of memory before routing responds.** All three defensible individually; together they mean "routing will not react to a fresh regime shift in less than a week." When the shift arrives and hurts, shortening one gate is the fix (v0.6.566 shortened the walker's).
- **Verify field semantics BEFORE recommending a threshold.** I told Joe "n ≥ 500 per day" without checking that the walker's `n` field is 30d rolling, not per-day. Caught it before coding — but had it not been caught, the fix would have been the wrong shape. See [[feedback_measure_before_concluding]].

## Clock-watches
- **09-10 evening**: walker's 3rd day of new-format data — first possible clearance in walker output.
- **09-11**: earliest live routing change (walker cleared → selector fit reads it → collector picks up new table).
- **09-12**: 7d window fully clears pre-kill data — expect 7d REGRESS fields to age out to at least WATCH.
- **09-15**: KILLED_LAYERS registry prunable (carried from morning session).
