---
name: ws-l3-skip-table
description: "07-14 v0.6.351c Stage 1 preview (10 SKIP cells) → **07-28 v0.6.386 re-cut ships 2 NEW cells** (frontal 24-47 +5.8%, pre_frontal 24-47 +8.0%, both clean halves). 8 of the 10 07-14 SKIP cells vanished from the fresh SKIP set — v0.6.370 asymmetric SKIP table (26 fc-bin cells, 07-20) already absorbed most of that damage; Stage 1 now measures residual L3 damage after asymmetric SKIP fires. Existing table entries (ne_flow 0-48, sea_breeze 0-12) left in place (potentially partially stale — ne_flow 24-47 now shows L3 HELPS −5.45%; SKIP is fail-safe so not urgent). See [[project_07_28_post_reboot]]."
metadata: 
  node_type: memory
  type: project
  originSessionId: 74becc06-fe2f-4d6a-af5c-9236cb08ecdd
  modified: 2026-07-28T16:45:24.740Z
---

## Motivating question

Joe: "shouldn't we just skip nw_flow?" (07-14 chat, after seeing ws marked ✗ in the Winning fields panel and walkforward wanting to flat-drop ws from L3_FIELDS).

Answer: per-cell verification says yes-and — nw_flow 24-47 is the biggest single-regime drag but not the whole story. calm and unknown regimes are also L3 poison across multiple bands.

## Ship path

- **Stage 0:** existing pooled reads in `h_regime_l3.py` (auto-runs in digest). Per-regime verdict: frontal −48%, calm −31%, sw_flow −15%, pre_frontal −12%, se_flow −5% all WIN. sea_breeze +3% flat. ne_flow +4% and nw_flow +6% L3 LOSES. But nw_flow's L3 LOSES was for the whole regime — needed per-band verification.
- **Stage 1 (07-14 v0.6.351c):** `analysis/h_ws_l3_regression_stage1.py`. Mirror of wg L3 Stage 1. Same halves-verified 30d/15d/15d architecture.

## Stage 1 verdict (07-14, MIN_N_CELL=200, floor=3.0%)

**10 SKIP / 20 KEEP / 4 MARGIN / 1 THIN / 2 PERSISTENCE_TERRITORY** of 37 judged cells.

**SKIP cells:**

| regime | band | pooled Δ | halves |
|---|---|---:|---|
| calm | 0-5 | +24.99% | +12.78 / +34.02 |
| calm | 6-11 | +59.61% | +33.14 / +77.01 |
| calm | 12-23 | +75.53% | +51.99 / +136.57 |
| calm | 24-47 | +73.29% | +65.58 / +87.52 |
| **nw_flow** | **24-47** | **+29.06%** | **+8.22 / +56.00** ← Joe's intuition per-cell |
| sea_breeze | 6-11 | +6.21% | +7.60 / +3.94 (already skipped v0.6.279) |
| sea_breeze | 24-47 | +17.39% | +27.90 / +5.20 |
| unknown | 6-11 | +8.09% | +8.66 / +5.23 |
| unknown | 12-23 | +28.38% | +24.35 / +48.77 |
| unknown | 24-47 | +45.52% | +40.44 / +65.25 |

**Key architectural learning:** nw_flow doesn't lose broadly — just at 24-47h. nw_flow 0-5, 6-11, 12-23 are all KEEP or MARGIN. A whole-regime `("nw_flow", 0, 48)` skip would have killed L3 on 3 regime-bands where it helps. Per-cell verdict beats the coarse "extend skip with whole regime" approach.

**ne_flow observation:** Stage 1 shows ne_flow KEEP everywhere (0.5%, +0.4%, −3.1%, +0.4%) — much closer to flat than the pooled Stage 0 +4% loss. But ne_flow all bands is already in the SKIP_TABLE (v0.6.279), so we're measuring "what L3 WOULD have done if applied." Existing ne_flow skip might now be over-cautious. Not a today-action but worth noting for a future re-audit.

## Proposed merged skip table

```python
SKIP_TABLE[("ws", "l3")] = [
    ("ne_flow",    0, 48),   # existing v0.6.279
    ("sea_breeze", 0, 12),   # existing v0.6.279
    ("calm",       1, 48),   # NEW Stage 1 07-14
    ("nw_flow",   24, 48),   # NEW Stage 1 07-14
    ("sea_breeze",24, 48),   # NEW Stage 1 07-14 (extends coverage; 12-23 stays KEEP)
    ("unknown",    6, 48),   # NEW Stage 1 07-14
]
```

After all skips, L3 still fires on ~77% of ws rows (frontal all, pre_frontal all, se_flow all, sw_flow all, nw_flow 0-23). Not a drop — targeted extension.

## Why this dissolves walkforward's "drop ws" verdict

Walkforward validator measures pooled MAE across all cells and asks "does dropping this field improve pooled?". Current: yes, because pooled damage from nw_flow 24-47 (n=23,341) + calm all bands (n=10,238) + unknown 6-47 (n=3,514) dominates. Once these cells fall back to L2 via skip table, the residual pool where L3 fires is the winners, and walkforward should flip back to KEEP.

## 7-day gate

- Day 1 = 07-14. Earliest ship = 07-21.
- Weekly re-run of `h_ws_l3_regression_stage1.py` in nightly digest refreshes cells.
- Any halves sign-flip in a SHIP cell demotes it out of the ship set.

## Related

- [[07-14-session]] — parent session.
- [[wg-l3-skip-table]] — sibling ship. Different field, same architecture, same 07-21 flip.
- [[feedback-regime-gate-first]] — the frame that justified per-cell over flat-drop.
- [[feedback-whitelist-promotion-gate]] — 7-day gate.
- [[ws-l3-long-lead-regression]] — the older Stage 0 diagnostic that identified nw_flow as a candidate months ago; this Stage 1 finally halves-verifies it.
