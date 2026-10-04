---
name: project-08-10-session
description: "2026-08-10 session. 2 live-layer ships (v0.6.401 chp diurnal + pr L2 regime-gated) + 10-script daily-digest retirement + c1 re-cure + full pr debug-page sweep + 3 investigations closed (wd transition penalty, pp source, cluster_spread). Big session, all shipped clean."
metadata: 
  node_type: memory
  type: project
  originSessionId: b8058893-d7b5-4544-a4d3-9f9dee94eef7
  modified: 2026-08-10T21:27:32.112Z
---

# 2026-08-10 session summary

## Ships (v0.6.401)

Two same-day investigations, both flagged for tomorrow-watch, both resolved same-day via existing pair-log data.

1. **chp diurnal gate** (`weather_collector/processors/ch_persistence_gate.py`). ch scoreboard 12-23h had climbed to +74.6% vs raw over 24h. 48h pair-log band-cut traced the +7.48 chp_bias to **daytime valid hours in nw_flow** (n=78, chp_bias +20.51) and **daytime valid hours in pre_frontal 24-47h** (n=91, chp_bias +4.25). Nighttime cells same regimes: -6 to -26% wins vs raw. Physical: post-frontal / pre-frontal residual overnight clouds burn off by midday; persistence over-forecasts. `_DIURNAL_SKIP_REGIMES = {nw_flow, pre_frontal}` + `_DIURNAL_SKIP_HOURS = [10, 18)` local. Diurnal skip count exposed as `ch_persistence_gate.diurnal_skips_by_band`. See [[project_ch_chp_midlead_band_watch_08_10]].

2. **pr L2 regime-gated SHIP** (`weather_collector/processors/corrected_hourly.py`). First live pr L2 apply since 07-01 kill. `pr_l2_regime_lead_retro` cleared halves on 8,596 August shadow rows (Jaccard 0.50): `(nw_flow, 0-5h)` A +21.8%/B +41.6%, `(nw_flow, 6-11h)` A +10.3%/B +13.1%. Conservative first ship — only both-halves winners. Pooled-only WINs (nw_flow/12-23h, pre_frontal/{0-5,6-11}, sw_flow/{0-5,6-11}) held pending 7-day gate agreement. Shadow-write unconditional. Scoreboard: pr dropped from `MAE_UNCORRECTED_FIELDS`; touched median n=8 → n=9. See [[project_pr_l2_regime_flip_investigation_08_10]].

## Digest retirement — 10 scripts to `.skip.py`

Dead-verdict daily-digest scripts with no reopen path:
- `h_ws_blend_hours_sweep` — SHIP verdict stale (constant already live).
- `cluster_spread_orthogonality` + `cluster_spread_smoketest` — parent KILL.
- `h_cloud_bias_persistence` — verdict itself said "stop calling it a live question."
- `h_pp_bin_calibration`, `h_pp_platt_calibration`, `h_pp_platt_by_regime`, `h_pp_frontal_platt_stage1` — all HOLD forever, halves divergent (Platt-family investigation parked 08-02).
- `h_pp_bias_persistence_stage0` — KILL.
- `r4_spread_analysis` — CLOSE.

Digest 134 → 124 scripts. Registry references cleaned up in `build_executive_summary.py` (KNOWN_LIVE_PIPELINES, SHIP_RESOLUTION_SCRIPTS, TOOL_QUESTION_GROUPS) and `pp_brier_reliability.py` (STAGE0_OPEN next-step pointer).

Criteria used (worth noting for future retirement passes): retire when (a) target constant/config is live and can't drift, or (b) same HOLD/KILL/CLOSE verdict for weeks with no reopen mechanism, or (c) the tool's own verdict declares the question answered. `.skip.py` naming keeps them runnable on demand.

## Investigations closed (no code change needed)

- **wd transition penalty** — pair-log workup on the +88-115% mismatch penalty (n=28,463 rows). L1 fallback vs top-of-stack is ±3-12% across bands; uniform-90° prior is +25-35% WORSE. Root cause: model got the regime wrong → every downstream layer inherits wrong inputs → no post-hoc fix. wdp already at current-optimal 4 SHIP cells. See [[project_wd_transition_penalty_investigated]]. Actionable UI intervention noted but deferred: at forecast time, `state_fc[lead] != state_curr` is detectable — widen displayed compass band on such leads. Needs PWA design call, not implemented.
- **pp source diagnosis** — pp prod_real ≡ raw every day (L1-only confirmed). Recent-week +44.9% ΔMAE is weather-mixture (more rain events); not model drift. No action.
- **cluster_spread axis_2 live check** — 52 SHIP cells across three quartiles. Q4 (high-spread) has 0 SHIP — dead subaxis. Q1 (10) + Q23 (42) productive. Axis earning its keep; retiring the daily monitor was fine.

## Followup cleanups

- **MLC sentry un-retirement.** `marine_layer_anomaly.py.skip` had been retired but the digest kept reading its 07-31 stale JSON and re-flagging the same "★ DECAY" alert every day. Fresh run today: verdict STABLE (in-bin -0.39 → -6.10). Un-retired to `.py` — `project_mlc_diagnosis` explicitly wants ongoing surveillance for "future ★ = new signal", which requires the actual daily sentry.
- **Debug page pp Platt row** (line 881 + 1002) — stale "07-27 Stage 1 SHIP" wording; updated to parked-state.
- **Layer-shape sentry** — was offline due to 08-10 AM DNS blip on data.wymancove.com. Cache refreshed; self-heals on next digest.
- **c1_calibration_audit** flipped PASS → HOLD morning digest (63% pass rate). Re-ran `c1_confidence_calibration.py` + `c1_curate_confidence_table.py`, deployed. 23 wired cells unchanged (16 SHIP / 7 MARGINAL); bin-level MAE refresh only.

## Debug page pr sweep (Rule 5)

Full sweep on the pr L2 transition from L1-only → regime-gated:
- pr row status column L1 → L2 additive gated
- L2 mesonet blend list updated
- L2 per-field rundown table DISABLED → RE-ENABLED row with regime-gate context
- ch row noted the diurnal gate + pointer to Post-ship watches
- Post-ship watches: two new v0.6.401 entries at top
- Recent activity: 08-10 (today) entry documenting all ships + retirement + re-cure

## Process fix (before ships)

`feedback_digest_triage_discipline` step 5 added — cross-check "Auto-relabeled STABLE / KNOWN_LIVE_PIPELINES", "Narrow-promote gates", and "walkforward_l3l4_validator" sections BEFORE recommending any SHIP-eligible action. Triggered by 3-days-running miss where I flagged already-live C1h cells as ship-ready. Reference 08-10 incident documented in the memory.

## Commits pushed (5)

- `a36fc88` v0.6.401 ships (chp diurnal + pr L2 gate)
- `10325a0` digest registry cleanup for retired scripts
- `72d1832` v0.6.400a top-level-forecast-is-L2 fixes (5 prior-session analysis edits)
- `cab7ab4` daily curated JSON refresh
- `10d7740` debug page pr L2 sweep
- `426497c` followup: pp Platt row parked + MLC sentry un-retire

## Pipeline-to-good plan

- Item #3 (cl root-cause fix / Lc recent-bias gate) — day 2/7 of ch's rolling gate. On track.
- No other items touched.

## Wins to note

- Two same-day investigations resolved same-day (not deferred to 08-11 morning). Pattern: when a signal warrants "wait one day," check if the pair log or shadow log already has enough data. Often it does.
- No correctness incidents this session (contrast 08-09 which had 4). Cross-referencing MEMORY.md before making claims worked.

Related: [[feedback_digest_triage_discipline]], [[feedback_verify_field_is_corrected]], [[feedback_check_own_arithmetic]], [[feedback_analysis_skip_naming]], [[feedback_curated_json_daily_drift]].

## PM session — audit + debug page (v0.6.401d, commit 70caf67)

**Memory hygiene wins** (biggest deliverable): the standing plan file was silently lying about state. Items 4 (Layer-tuple sanity test) and 5 (Digest action-list at top) were both marked [not-started] but had actually shipped 08-04 in v0.6.390k. Discovered by looking before writing (`tests/test_layer_tuple_sanity.py` already existed with 6 passing tests; the digest already had 🚨 TOP ALERTS at build_executive_summary.py:959-981). Would have re-implemented both from scratch without checking. Same class as CLAUDE.md rule 4 (verify before recommending). Updated plan file: 4/5 shipped, 2 deferred (Joe: leave wd UI alone), 3 in-progress.

**MEMORY.md watch-date sweep:** 8 entries clearly said CLOSED/SHIPPED in text but sat in Active. Moved to Settled: h L2 shape retune, chp mid-lead regression, ch chp mid-lead band 08-10, wd transition penalty investigated, ws L3 long-lead regression, pr L2 regime-gate opportunity, pr L2 regime-flip investigation 08-10, pa investigation. Then verified wdp watch (14-day window closes today) — anomaly detector CLEAN, both bands CALIBRATED ±4.5%, no post-ship watch alerts. Moved wdp to Settled as 9th entry. Also unblocked wd L3+L4 circular plan ("Blocked until wdp watch clean" → "Unblocked 08-10").

**Debug page v0.6.401d (three changes):**
1. Staleness audit block above "Right now": hand-curated OPEN_WATCHES array; hidden when no watch is past its closeDate; anti-fossilization pattern mirroring digest 🚨 TOP ALERTS.
2. renderWatchDayCounters enhancement: added `CLOSES TODAY` (amber) + `Xd OVERDUE — resolve` (red) states. Prior "closed" green flag on day > window falsely implied clean.
3. Archived Post-ship watches relocated: was an inline `<details>` under "What's improving," now lives at `#sec-archive-post-ship` inside the existing global Archive section. Left an in-place pointer link for wayfinding.

**Failed build (removed same-turn):** standing plan tickler at top of Current state. Rendered 1 open item padded with 4 historical rows; Joe: "I don't see the point." Correct read — the digest already surfaces item 3 daily, the plan file is deliberately strategic (5 long-arc items) while tactical work runs across ~124 daily diagnostics + sentries + post-ship watches. Don't build UI that duplicates the digest layer. See new feedback [[feedback_dont_duplicate_digest_layer]] + [[feedback_archived_content_in_archive_section]].
