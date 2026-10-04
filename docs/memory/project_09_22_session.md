---
name: project-09-22-session
description: "09-22 Tue — 2 commits. Analysis: Stage 1.5 co-axis gate script for inter_model_spread vs xr_q (848cef9e). Ship: v0.6.647 l3_nbm skip-ADD 3 wd cells two-window CONFIRMED (6ca4cae5). Collector deploy verified clean."
metadata: 
  node_type: memory
  type: project
  originSessionId: a3b1b523-3714-4fec-a95b-290a3dd60c84
  modified: 2026-09-22T14:08:10.935Z
---

# 09-22 Tuesday session

## Ships

**v0.6.647 (6ca4cae5) — l3_nbm skip-ADD 3 wd cells.** Data-only change to `weather_collector/data/skip_table_nbm_curated.json`; runtime reads via `skip_table_nbm.py` at collector import. All three cleared v0.6.574 two-window gate:
- `wd/pre_frontal/0-5h`: 14d n=343 -3.10%, 50d n=914 -3.01%, halves -3.08/-2.94 both-negative.
- `wd/ne_flow/12-23h`: 14d n=212 -9.30%, 50d n=762 -5.80%, halves -12.68/-3.43 both-negative.
- `wd/ne_flow/24-47h`: 14d n=294 -6.20%, 50d n=1,077 -3.81%, halves +0.00/-4.05 directionally-consistent.

**Post-deploy watch: wd/ne_flow/24-47h.** Its h1 half is neutral (+0.00%), not strictly both-negative. Thinnest evidence of the three. First cell to look at if `nbm_regression_sentry` or `nbm_skip_earning_audit` surfaces regression.

wd stack now covers 6 regime×band cells: se_flow (0-5, 6-11, 12-23) shipped v0.6.500–v0.6.609; today adds pre_frontal/0-5 + ne_flow/12-23 + ne_flow/24-47.

**Deploy verification**: `gcloud functions logs` showed new instance rolled at 13:53:42 UTC, first tick under new code (execution `3eJzRqOJTv6j`) completed 13:58:23 UTC clean. Silent skip fires (no per-fire log line); rely on tomorrow's digest to score.

## Analysis (not shipped to runtime)

**848cef9e — `analysis/h_inter_model_spread_vs_xr_q_ortho.py`**: Stage 1.5 co-axis gate built. Anchors [[project_09_22_ims_vs_xr_q_stage15]]. Day-1 result: **15 of 28 SHIP cells cleared xr_q conditioning** — dp × 4 + h × 4 + t/{6-11h, 24-47h} + wd/24-47h + wg/{6-11h, 12-23h} + ws/24-47h + cc/0-5h. 3 correctly REDUNDANT (cc/24-47h, wd/6-11h, wd/12-23h). 10 THIN (ch chronic + wg gray-zone). Script auto-runs in daily digest starting tomorrow. Earliest wire 09-29 pending 7-day PASS-set stability.

## Strategic context (not new, but load-bearing for tomorrow)

Today started from digest showing SHIP-ELIGIBLE=none but strong pre-gate evidence in several places. Two "obvious" ship candidates went sideways:

1. **NWS 3-way selector for dp (5 walker-cleared cells)** blocked at wire time by the v0.6.600 dp-derived coherence guard in `l1_selector.py:37-45` (`_NWS_FIELDS_WIRE_ELIGIBLE = frozenset({"t", "ws", "wd", "pp"})` — dp excluded). Real unblock is a coherence wire (back-derive h from NWS-dp, or gate on NWS-t agreement); ~1 week of work, not a same-day ship.

2. **inter_model_spread → C1 axis 6 (28 Stage 2 SHIP cells)** blocked pre-wire by missing co-axis ortho vs live xr_q (both signals overlap 6/6 fields, both are difficulty proxies). Built the Stage 1.5 gate to sort it — 15/28 passed. That's now on the 7-day path.

Held on **h_h_residual_persistence flip** (walker 6 cleared / 7 flipped — wg flipped LIVE at 16 cleared / 3 flipped, cleaner ratio). Reconsider next session.

## Immediate next steps (fresh session pickup)

1. **Post-deploy watch on v0.6.647.** Read tomorrow's `nbm_regression_sentry` + `nbm_skip_earning_audit` for wd. Flag wd/ne_flow/24-47h first.
2. **Day 2 of Stage 1.5 gate watch.** Digest will emit `h_inter_model_spread_vs_xr_q_ortho.json` fresh tomorrow. Check PASS list stability vs today's 15 cells.
3. **cc_combine walker.** Yesterday's day 2/2 out-of-sample stability was set; today walker still shows 1/30 cleared (pre_frontal/0-5). Candidate for `CC_COMBINE_GATE_ENABLED = True` if the walker clears cleanly a day or two more.
4. **h_h_residual_persistence flip re-eval.** Same-shape as live wg (+34.9%). 22 days pre-staged. Reason to hold today was walker turbulence (7 flipped) — decide if that's a real signal or noise across the next 2-3 digests.
5. **NWS coherence wire scoping.** Draft `analysis/nws_dp_coherence_scout.py` extension to test the two paths (back-derive h vs t-agreement gate) against 30d pair log. Real ship candidate if scoped properly.
6. **wd l3_nbm HOT sentry** — layer help +2.7% → -5.0% (Δ +7.7pp). Today's ship removes wd L3 correction from 3 more cells; expect this to improve. Watch the sentry trend day-over-day.

## How to apply

**Rule** (adds to [[feedback_orthogonality_gate]]): when a new C1 axis's Stage 1 orthogonality gate misses a live incumbent axis it overlaps with, don't wire — write the missing gate first. Stage 1 gates are starting points, not promotion gates. Confirmed with today's ims/xr_q catch: 3 of 28 cells were REDUNDANT with xr_q; would have shipped double-widening.

**Rule** (adds to [[feedback_answer_direct_first]]): when I catch myself calling something "shippable today" without checking whether the digest's own SHIP-ELIGIBLE gate has cleared, retract the framing before proceeding. The digest's `SHIP-ELIGIBLE: none` line is the strict bar; my judgment substituting for it is exactly the cowboy mode CLAUDE.md warns against. Distinguish "gate-cleared" from "well-evidenced pre-gate" explicitly. Joe caught this today.
