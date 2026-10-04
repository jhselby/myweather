---
name: 07-14-session
description: "Tuesday marathon — 8 commits (v0.6.351 → 351f). Ship-vein day: 3 skip-table Stage 1 previews (wg L3, ws L3, t L2 — first is Discovery, second validates Joe's nw_flow intuition per-cell, third confirms t at ceiling). wg residual persistence Stage 3 wired ENABLED=False. ch persistence LANDMARK answered — keep the shipped gate. Lt cleanup: divergence-report row + full R&D section rewrite (was still saying 'Path back — Fix B' 24h after Fix B failed). New Rule 5 (transition-invalidation sweep) codified in feedback_debug_page_canon after Joe caught the Lt staleness. Debug page category-tag redesign (DISCOVERY/INFRASTRUCTURE/DASHBOARD/PIPELINE). 07-21 now stacked with 6 potential ship decisions."
metadata: 
  node_type: memory
  type: project
  originSessionId: 74becc06-fe2f-4d6a-af5c-9236cb08ecdd
---

## The arc

Started 07-14 morning with the daily digest surfacing today's findings. Ended after 8 commits + memory hygiene.

**Two novel discoveries + one confirmation-at-ceiling + one landmark closure:**
1. `wg L3 skip-table Stage 1` — 6 SKIP cells halves-verified (calm all bands, sea_breeze 0-5, unknown 24-47).
2. `ws L3 skip-table Stage 1` — 10 SKIP cells (calm all, **nw_flow 24-47 +29% halves +8/+56 validating Joe's per-cell intuition**, sea_breeze 6-11 + 24-47, unknown 6-47).
3. `t L2 skip-table Stage 1` — 0 SKIP / 30 KEEP: t is at ceiling. L2 saves 20-30% at short leads, tiny +1-2% noise at long leads, no per-cell extractable damage.
4. `ch persistence LANDMARK answered` — persist_only vs regime_gate: pooled tied within 0.14%; gate wins halves-hedge. Keep the shipped gate.

**Two Stage 3 wires (both ENABLED=False):**
1. wg residual persistence gate — 6 SHIP long-lead flow-regime cells (frontal/pre_frontal 24-47, se_flow 12-23+24-47, sw_flow 12-23+24-47). Earliest flip 07-21.
2. (nothing else Stage-3 wired today; the two L3 skip-table Stage 1 previews aren't wired yet.)

**Infrastructure cleanup:**
- `Lt divergence-report fix` — was reading r5_cove_analysis "SHIP" (against L1), producing recurring "GATE CLEARED (2/2)" false-positive. Now reads l6_fix_b_refit HOLD, shows AGREE.
- `Lt R&D section rewrite` — was still labeled [DORMANT LAYER] with "Path back — Fix B" a full day after Fix B was answered and Lt was retired 07-13. Joe caught this ("why the flying fuck does the page say the path back is B?"). Section rewritten to [RETIRED LAYER] with "Fix B tried, failed" + Reactivation criterion.
- `Debug page category tags` — DISCOVERY / INFRASTRUCTURE / DASHBOARD / PIPELINE prefix tags (muted small-caps colored) replaced leading ✓/★ symbols in Recent activity for scan-ability.

**New rule codified:** Rule 5 (transition-invalidation sweep) added to [[debug-page-is-canon]]. After Joe caught the Lt "Path back — Fix B" staleness that survived multiple debug-page sweeps because those only touched top-summary sections and skipped R&D subsections 1800 lines deep. Rule: after any status transition, grep the ENTIRE debug page for old-status keywords and update every hit in the same commit. Codified with concrete grep targets per transition type (retirement, ship promotion, verdict flip, skip cell change, failed refit). Immediately validated: after codifying, applied rule against Lt and caught 6 more stale references (line 1921 prose, HTML comments, JS labels, live-widget text). Then applied broader to all today's transitions (v0.6.351f) and caught 4 more (ws day counter, ch day counter, Lc day counter, C1h/C1d earliest ship).

**07-21 is now a landmark day** — 6 potential ship decisions all converge:
- ch persistence gate flip (7-day clock started 07-12)
- cl persistence short-lead gate flip (7-day clock started 07-13)
- wg residual persistence gate flip (7-day clock started 07-14 today)
- wg L3 skip-table extension (7-day streak started 07-14 today)
- ws L3 skip-table extension (7-day streak started 07-14 today) — would dissolve walkforward "drop ws" flat verdict
- C1h + C1d narrow-promote (both reset today to day 1/7 due to SHIP set change)

## Ships (in chronological order)

- **v0.6.351** — wg residual persistence Stage 3 wired ENABLED=False. Processor `wg_residual_persistence.py`, curated JSON with 6 SHIP cell verdicts + 24-slot hour-of-day L2-residual correction table. Runs AFTER decay_apply so it overrides L3.
- **v0.6.351a** — ch persistence LANDMARK answered — keep the shipped gate.
- **v0.6.351b** — wg L3 skip-table Stage 1 preview + Lt stale-gate divergence-report fix (bundled).
- **v0.6.351c** — ws L3 skip-table Stage 1 preview + debug page category-tag redesign (bundled).
- **Standalone commit** — Lt R&D section rewrite from DORMANT/Path-back to RETIRED with Fix B answered.
- **v0.6.351d** — t L2 skip-table Stage 1 preview — confirmed at ceiling.
- **v0.6.351e** — Rule 5 sweep: 6 more stale Lt refs caught by grep after codification.
- **v0.6.351f** — Rule 5 broader sweep: 4 more stale reference-section refs across ch/ws/Lc/C1h+C1d.

## Related

- [[wg-residual-persistence]] — the day's Stage 3 ship, memory rewritten from Stage 1 MARGINAL to Stage 3 SHIPPED.
- [[ch-persistence-gate-ship]] — landmark answered, memory updated with head-to-head numbers + 07-14 SHIP-set flex.
- [[wg-l3-skip-table]] — new memory for today's Stage 1 read (candidate for 07-21 ship).
- [[ws-l3-skip-table]] — new memory for today's Stage 1 read (candidate for 07-21 ship, dissolves flat-drop verdict).
- [[t-l2-ceiling]] — new memory for today's ceiling verdict (closed thread; don't re-litigate).
- [[debug-page-is-canon]] — Rule 5 codified today.
- [[Lt-fix-b-answered]] — Lt retirement confirmed 07-13; today closed the stale-reference cleanup.
- [[07-13-session]] — parent session (novel wg finding + Lt Fix B answer).

## Skill vein observation

Joe's question mid-session: "shouldn't skip table work be our primary improvement mechanism?" Discussion: yes while the vein is rich, but skip tables subtract while other mechanisms add. Current pattern: 5 recent ships in a row have been the "regime-heterogeneity → halves-verified Stage 1 → per-cell ship" shape. Predicted 2-4 more weeks of skip-table-dominant cadence before the vein runs out, then mix shifts to gates + specialists + new signal (like today's wg residual persistence gate, which ADDS rather than SUBTRACTS).
