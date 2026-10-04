---
name: project-07-27-session
description: "2026-07-27 (Mon) session log. 9 ships total: v0.6.382 wdp flip ENABLED=True (largest single-field flip since Lc) + 8 debug-page cleanup passes (v0.6.382a → v0.6.382h). Cumulative debug-page impact: ~450 lines net removed, ~40 stale references fixed, ~3-way R&D reorg, RIGHT NOW pipeline table split into 2 columns, Open architectural questions trimmed 11 → 2. Two new feedback memories added on R&D sweep hygiene."
metadata:
  node_type: memory
  type: project
  originSessionId: 222946da-f295-4807-baf0-368c6663308b
  modified: 2026-07-27T16:28:49.847Z
---

## Ships (9 today)

### The actual flip
- **v0.6.382 — wdp FLIPPED ENABLED=True.** 7-day gate cleared (Jaccard 1.0 across 5 daily reads 07-20 → 07-26; SHIP set bit-stable at 5 cells). Executed [[docs/preflight/wdp_ship_patches.md]] verbatim across 7 sites (30-min copy-paste as designed). Post-deploy 07:37 EDT: `enabled=true`; snapshot has full wd layer stack `{wd_l1, wd_l2, wd_l3, wd_l4, wd_wdp, wd_applied}`; `wd_applied` first-24 leads `{l2: 16, l1: 8}`. **Zero fires today** because `state_curr=calm` and no fc_regime transition matches a SHIP cell at its band — expected for this morning's regime shape.

### The 8 debug-page cleanup passes
- **v0.6.382a — post-ship sweep.** Recent activity rolled + INFRA v0.6.381 added to 07-26; 07-24 → 07-21 trimmed. Calendar 3 resolved rows removed. wdp added to Post-ship watches; wd persistence gate + wg residual persistence sections rewritten; course-of-action framing updated.
- **v0.6.382b — compression pass.** Cut "Upcoming decisions" sub-box (Calendar covers it); compressed Production stack specialist bullets to one-liners with cross-refs; "What's improving" chp/Lc/wdp cut (shipped, not improving); ws L3 REPLACEMENT rewritten to lead with pending flip. ~140 lines removed.
- **v0.6.382c — per-field snapshot moved.** From under Engineering to top of Current state (it's the granular version of "what's running"). 3 stale rows fixed: h retest declined, dp gains dp_residual_persistence wire, cl updated to clp successor.
- **v0.6.382d — Open arch cleanup + RIGHT NOW 2-column split.** Open architectural questions trimmed 11 → 2 open + pointer for 6 settled. Retired sub-box deleted (Archive covers it). RIGHT NOW pipeline table split into 2 columns with correcting-first partition — old vertical 14-row table → 7 rows × 2 columns; today's snapshot col-1 = 7 correcting fields (t/h/dp/ws/wg/cc/cm), col-2 = 7 quiet (wd/cl/ch/sr/pp/pa/pr). Partition-only (not sort-by-magnitude) chosen because unit heterogeneity makes raw-magnitude ranking misleading.
- **v0.6.382e — Recent activity condensation.** Badge legend collapsed to single line; today's 3 DASHBOARD entries consolidated into one pointer-to-CHANGELOG line; deleted hidden HTML comment block preserving 07-24 → 07-21 trimmed items.
- **v0.6.382f — per-band tables Prod header.** Header shortened from "Production" to "Prod" to fix column overflow (Joe noticed at zoom-out that "Producti…" was truncated on multiple cards). Reverted an earlier box-shadow backstop that was papering over the wrong problem.
- **v0.6.382g — R&D + Archive full sweep.** ~40-50% character reduction. G1 C1 mega-paragraph compressed; Backlog "in-flight" table deleted (duplicate of What's improving); Group B marine-layer 1500-char paragraph → 3 lines + Archive pointer; Group D shipped items to one-liners; Stage 0 Experiments 14 → 7 open items; R0/D1/S1/B1/F1 preambles tightened.
- **v0.6.382h — R&D 3-way regroup + RIGHT NOW right-col fix + Engineering meta-line delete.** R&D restructured from 2-way (Diagnostics/Candidates) to 3-way (**Diagnostics** = audit views: R0/D1/F1/R2; **Tools** = evaluation instruments: S1/B1; **Candidates** = in-flight hypotheses: C1 stack + Backlog + Experiments). Joe's key insight: G1 "Gated correction candidates" label was redundant since all Stage 3 candidates are gated by definition — renamed to "C1 confidence stack — status" under Candidates. R6 standalone deleted, absorbed into C1 stack card + S1 tool description. Also fixed RIGHT NOW right-column label styling (td:first-child CSS didn't match the 5th td, so right-column labels rendered default color instead of muted grey — added inline style). Engineering meta-line deleted (orphan pointer to old layout).

## Debug page — final structure

- **Current state** = per-field snapshot at top + tri-column What's running / improving / evaluated
- **Recent activity** = rolling 3-day window with 1-line badge legend
- **Engineering updates** = 3 sub-boxes (Production stack, Built-not-applied, Open architectural questions — 2 items only, Retired sub-box deleted with pointer to Archive)
- **R&D** = 3-way split (Diagnostics for audit views / Tools for candidate evaluation / Candidates for in-flight work)
- **Archive** = single source of truth for all settled/killed history

## 07-27 flip triage outcome

- **wdp ✓ SHIPPED** — Jaccard 1.0 → executed preflight → post-deploy verify clean
- **ws L3 REPLACEMENT ⚠ HELD** — asymmetric Jaccard 0.75 < 0.80; re-eval ~07-31
- **wg residual persistence ⚠ HELD** — Stage 1 flipped PROMOTE → MARGINAL 07-26 (+20.24%, was +17.74%); persistence hypothesis's own aggregate signal weakened. Hold until Stage 1 recovers PROMOTE.
- **wg L3 skip-table extension ⚠ HELD** (paired with wg residual persistence)

Course-of-action framing: was "4 flips clustering at Mon 07-27, largest single-day flip since Lc if all clear" → single-ship outcome.

## Persistence specialist family — trigger for helper extraction

Post-flip: three concrete persistence specialists — **chp** (ch, 07-19 v0.6.358), **clp** (cl, 07-24 v0.6.379 ENABLED=False pending 07-31 flip gate), **wdp** (wd, 07-27 v0.6.382). Shared `persistence_specialist(field, gate_table, obs_source, fallback_key, math="linear"|"circular")` helper extraction on deck per [[project_todo]] P4 item 10 — three concrete cases now enough to justify the abstraction (two wasn't).

## New feedback memories written

- [[feedback_rd_sweep_on_verdict_change]] — when a candidate script's verdict flips (MIXED → PROMOTE, KILL, etc.), sweep the R&D section at the same time as top-of-page counters. Trigger: same digest that surfaces the flip. Bulk-apply monthly if not caught in flip triage.
- [[feedback_shipped_items_leave_backlog]] — when a candidate hits Stage 3 (wired ENABLED=False) or Stage 4 (shipped), it exits R&D Backlog entirely. Detail lives in layer section / Post-ship watches / What's improving. Backlog holds only Stage 0-2 pre-wire ideas. Prevents preamble examples going stale (e.g. Lc-as-gated-example after Lc flipped).

## Debug page chart (visual sanity)

Joe examined the wd accuracy chart on live debug page: shows Raw + L2 blend + 7d means only — **wdp and prod_real absent** because both have 0 days of pair-log history. `MIN_DAYS_FOR_LEGEND = 3` gates them out. `layersForField()` isProd-fallback promotes L2 blend → rolling mean draws off L2. Right-edge dashed vertical near 2026-07-27 confirms SHIP_EVENTS.wd entry firing. Same behavior chp had 07-19 → 07-22. wdp + prod_real lines appear ~07-30 (day 3).

## Discussions worth retaining

**F1 Frontal passage log purpose** (Joe asked mid-session): `frontal_events_log.json` is consumed by (a) PWA front-passage card via briefing, (b) C1e confidence axis SHIPPED 07-01 v0.6.272 (classifies live tick as post <24h or baseline ≥24h; stamps `weather_data.confidence.live_axes.hsf_group`), and (c) ~10 analysis scripts (h_hours_since_front, h_hsf_orthogonality, h_pre_frontal, h_pre_front_orthogonality, h_front_type, h_c1h_orthogonality, h_cloud_disagreement_orthogonality, h_precip_fc_orthogonality, c1_stage4_audit, c1_confidence_calibration_v2). C1e is one of the 5 axes feeding the multi-axis Stage 4 calibration audit; applied=False at display layer because C1 as a whole hasn't cleared Stage 4 (07-26 audit: HOLD 32.43%).

**Partition-vs-sort-by-magnitude for RIGHT NOW table** (Joe raised sort as alternative): rejected sort-by-magnitude because unit heterogeneity (%pts vs mph vs °F vs W/m²) makes raw ranking misleading, and normalizing by relative % breaks on raw=0. Kept partition-only; simple, stable, no unit gymnastics, still puts today's signal at top-left and today's noise at bottom-right. Joe agreed.

**All-candidates-are-gated insight** (Joe raised): Stage 3 = wired ENABLED=False by definition. The "Gated candidates" label as a separate R&D bucket was redundant. Drove the C1 stack card rename in v0.6.382h.

## Memory adds

- This session log (extended)
- [[feedback_rd_sweep_on_verdict_change]] (new)
- [[feedback_shipped_items_leave_backlog]] (new)
- [[project_todo]] refresh required (needs day-counter advance + WCSI backlog note preserved earlier)
- [[project_wd_l2_blend]] — wdp is the follow-on specialist; note the interaction (wdp overwrites L2 on gate-fired cells)

## Follow-through for next session

- **07-28 (Tue) — first digest with SKIP-aware walkforward.** Verify divergence report shows AGREE on wg (previously spurious drop signal via v0.6.381 fix). `drop ws` may persist as real (not spurious) marginal signal.
- **07-28 — chp mid-lead re-check** deferred from 07-25. If aggregate persistence-skill Δ moves outside [−1.2, −0.7] by 07-28 → force ad-hoc per-lead script vs `forecast_l6`.
- **07-28 — wg residual persistence gate first re-check** post-HOLD. Watch for Stage 1 hypothesis recovery from MARGINAL → PROMOTE.
- **07-30 — C1 Stage 4 re-audit.** Unblocks C1h (14/7 CLEARED) + C1d (3/7). cl mixture-check needs ~4-day window roll.
- **07-31 — Lc 14-day watch closes; clp 7-day flip gate closes; ws L3 REPLACEMENT re-eval (Jaccard cell-set needs 3-4 more days to settle).**
- **08-01 — dp residual persistence 7-day flip gate closes.**
- **08-02 — ch persistence 14-day watch closes; h/L4 narrow-add re-test after cl-window clears.**
- **08-03 — wd L2 + ws asymmetric-additive 14-day watches close; wd L3/L4 Stage 0 first honest read.**
- **08-10 — wdp 14-day post-ship watch closes.**
