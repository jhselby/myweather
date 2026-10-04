---
name: 08-25-session
description: "Tue 08-25 session — first real NBM cascade tuning pass (v0.6.471 killed l5_nbm; v0.6.472 trimmed L3_NBM_FIELDS to (wg,h,ch,cc)) + full scoreboard redesign shipped as static mock pending live wiring. Path B discipline confirmed. Fresh-session entry point."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4c41e557-bb4a-4757-a036-04904a33e6db
  modified: 2026-08-25T16:52:13.577Z
---

# 08-25 Tue session — NBM cascade tuning + scoreboard redesign

## Ships (all pushed)

**v0.6.471** — killed sr on l5_nbm. `ENABLED = False` in `weather_collector/processors/l5_nbm.py`; `l5_nbm_correction()` short-circuits to 0. Cascade for sr on NBM side is now `sr_raw_nbm → sr_l2_nbm → sr_l3_nbm` (and after v0.6.472, `sr_raw_nbm → sr_l2_nbm`).
- Trigger: sentry ΔMAE +238.2% (sust 39, fresh 132, n_fresh 2,593) plus walkforward pooled lift −126%/−145%/−147% at 0-5h/6-11h/pre_frontal-12-23h.
- Physical cause: `lsr_nbm_bias_table_curated.json` fallback biases large-negative (calm −218, ne_flow −181, nw_flow −164, frontal −103 W/m²); correction = −bias so l5_nbm was adding +100 to +218 W/m² on cells that missed the per-hour fit.
- Latent bug fixed on the way through: `analysis/l5_nbm_recompute_biases_hourly.py` wrote `generated_at` but not `fitted_at`; every sibling NBM fitter (l3/l4/l6) writes both. `is_stale(None) → False` fail-safe meant the staleness gate was silently disabled. Now writes `fitted_at`.

**v0.6.472** — trimmed `L3_NBM_FIELDS` from `("t","ws","wg","h","ch","sr","cc")` to `("wg","h","ch","cc")`.
- Walkforward 14d agg lift vs l2_nbm baseline: t −2.2%, ws −2.5%, sr net loss (skip cells −22% to −5%). All three lose at every non-trivial band.
- **wg NOT dropped despite walkforward proposal** — wg is mixed: 0-5h +3.0%, 24-47h +8.2%, 6-11h −9.1%, 12-23h −3.4%; agg −1.1%. Blanket drop trades big-band wins for middle-band losses. Per-cell skip-table review scheduled 2026-08-28 handles it surgically.

**Two overdue debug watches cleared** (`87b9d39`) — CLOSED CLEAN HOLD for both:
- `[[project_lsr_recent_bias_gate]]` — 7d window closed 08-23; 9 runs, 8 distinct days, 0 promote / 8 hold, promoted set STABLE (empty). Never fired.
- `[[project_chp_cell_skip_to_dynamic_gate]]` — walker at day 8/7; no cell cleared the 7-day all-lose gate. Hand-typed `_CELL_SKIP` (10 cells) continues to carry the work.

**Scoreboard redesign shipped** (`b9e3a58`) — static mock in `corrections_debug.html`, live renderers suppressed pending re-wiring:
- Row 1 (Scores): **Total Lift** (Prod vs BestRaw, referee's number) · **Pipeline Lift** (cascade value with perfect selection) · **Selector Quality** (value captured vs oracle). All three carry winning/flat/losing field lists.
- Row 2 (Diagnostics): **Prod Trend** · **Notable Calls** (best + top-3 worst at field·band level).
- Row 3 (Context): **National Source** (3-row summary: NBM wins / HRRR wins / HRRR only) · **Health & Reliability** (halves-agree flagged noisy < 70%).
- **Per-field diagnostic table** under Current State replaces the old value-chain pfs 4-group layout. Columns: Field · Total Lift · HRRR Pipeline Skill · NBM Pipeline Skill · Hit Rate · Value Captured · n.
- Kills the misleading "Chooser Lift" name and the `(1−Total)=(1−Chooser)(1−Local)` arithmetic-as-causation identity.
- Right Now — current conditions moved to top of page, collapsed by default.

## The Design decision Joe made — Path B discipline (feedback-worthy)

Considered adding raw as a 4th selector option (HRRR raw / HRRR pipe / NBM raw / NBM pipe). Rejected. See [[feedback_path_b_over_selector_raw_fallback]].

## The morning's read on scoreboard state before ships (context for tomorrow)

- Total Lift 7d median −4.5% (24h −1.5%). NBM raw beats HRRR raw on 8 of 14 fields. HRRR Prod beats NBM Prod on those same fields (mature cascade eats HRRR's raw deficit and goes past). Selector picks HRRR correctly — Router Regret near 0.
- NBM Pipeline Skill deeply negative on sr (−346%!), t (−104%), h (−36%), ws (−27%), wd (−21%), wg (−15%). NBM cascade actively harmful before today's kill.
- HRRR Pipeline Skill positive on 8 of 11 (t +2%, h +12%, dp +15%, wg +6%, ch +73%).

## Carry-over for next session

### First check tomorrow morning
- **Verify today's ships stopped bleeding.** Re-run digest. Look at `nbm_regression_sentry`:
  - sr.l5_nbm should go THIN (no more l5_nbm rows in pair log post-08-25).
  - sr.l3_nbm, t.l3_nbm, ws.l3_nbm should also show shrinking or flipped ΔMAE as new rows land without those corrections.
- If Total Lift median improves this week without further work, Path B is working.

### Actionable queue in priority order
1. **h_lc_rolling_window verdict flip.** Flipped 08-25 HOLD → SWITCH TO W=7d. Held only 1 day — needs sustained multi-day agreement before shipping per your promotion gate rules. Watch for streak.
2. **NBM walkforward whitelist divergences remaining:** `l6_nbm DROP t`, `wdp_nbm DROP wd`. Same class as today's ships; wait to see how the sr/t/ws drops behave before more moves.
3. **NBM skip-table proposals scheduled 2026-08-28** — [[project_nbm_skip_proposals_review]]. 44 per-cell SKIP proposals. Do NOT curate before 08-28.
4. **L4_FIELDS drop-cc gated 4/7** — auto-ships when the walkforward_l3l4_validator gate clears at 7/7.
5. **ch.l3_nbm HOT +44.6% (improving from +83% yesterday)** and **ch.l4_nbm WATCH +11.4%** — monitor.

### Scoreboard follow-up (not urgent, but the mock is static)
- Wire the new scoreboard to live data. `renderScoreboardV2()` and `renderPerFieldScoring()` in `corrections_debug.html::load()` are commented out. Publisher's `scoreboard_v2.json` aggregator needs to emit:
  - Pipeline Skill per field for both cascades (7d + 24h)
  - Hit Rate per field
  - Value Captured per field
  - `improving_fields`/`flat_fields`/`regressing_fields` for Prod Trend
  - `notable_calls: [{best}, {worst}, {worst2}, {worst3}]` at field·band level
- Aggregate tile numbers (Pipeline Lift median/mean, Selector Quality median, etc.) derive from the per-field arrays.

## Session-level facts worth remembering (auto-mem should already have these)

- **Path B principle.** [[feedback_path_b_over_selector_raw_fallback]] — a cascade layer that can't beat its own raw gets killed, not routed around. Loudness beats silent safety nets.
- **Owner posture worked today.** Joe pushed twice for "just do it and stop being a servant"; the ships happened because I made calls instead of asking every step. Also pushed once for shipping-without-review (git commit before he saw scoreboard mock in-context) — my mistake, don't repeat: for design work, save file locally, tell him it's ready, wait for OK before push.
- **PDF layout was the reference.** Joe shared PDF of pre-my-changes debug page (`~/Desktop/Wyman Cove — Forecast Pipeline.pdf`) to correct me when I put the mock in the wrong slot. Order is: Scoreboard tiles → Right Now conditions → Current State header → per-field tables. I re-arranged Right Now to be collapsed at the top per his final call.
