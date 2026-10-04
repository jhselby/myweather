---
name: project-chp-narrow-to-0-5h-watch
description: "chp is net +7.79% worse than L6 over 66d post-Lc window, driven by 6h+ leads. Band pattern is clean: 0-5h wins, 6h+ loses. Ship candidate: narrow chp to 0-5h only. Day 1 of 7-day watch, anchor 2026-09-21."
metadata: 
  node_type: memory
  type: project
  originSessionId: d9396da2-0b4a-4ad5-880f-066560d5a914
  modified: 2026-09-21T15:10:44.271Z
---

# chp narrow-to-0-5h — ship candidate on 7-day watch

## Anchor read 2026-09-21 (post-Lc window 2026-07-17 → 2026-09-21, 66 days, 23,820 paired ch rows across 22 live chp cells)

**Net effect of live chp on ch MAE: +7.79% (13.54 vs L6 12.56).** chp is actively degrading ch forecasts on 79.4% of the rows it touches. Only 14.8% show chp better.

**Band-pattern is clean.** 0-5h wins, 6h+ loses, driven by persistence signal decay past the short-lead sweet spot:

| Cell | n | chp | L6 | Δ | verdict |
|---|---|---|---|---|---|
| nw_flow/0-5 | 811 | 6.15 | 9.53 | **-35.5%** | BETTER |
| pre_frontal/0-5 | 568 | 9.37 | 16.22 | **-42.3%** | BETTER |
| sw_flow/0-5 | 865 | 8.51 | 12.38 | **-31.3%** | BETTER |
| se_flow/0-5 | 571 | 10.46 | 11.46 | -8.7% | BETTER |
| calm/12-23 | 476 | 9.14 | 9.62 | -5.0% | BETTER (only non-0-5) |
| ne_flow/6-11 | 244 | 11.41 | 11.98 | -4.8% | BETTER |
| nw_flow/6-11 | 736 | 8.90 | 8.98 | -0.9% | EVEN |
| ne_flow/0-5 | 130 | 12.36 | 12.41 | -0.4% | EVEN |
| frontal/12-23 | 177 | 13.58 | 13.58 | 0.0% | EVEN |
| frontal/24-47 | 323 | 8.72 | 8.72 | 0.0% | EVEN |
| pre_frontal/6-11 | 682 | 14.04 | 13.77 | +1.9% | WORSE |
| se_flow/12-23 | 2223 | 15.15 | 14.26 | +6.2% | WORSE |
| pre_frontal/12-23 | 1426 | 13.33 | 12.54 | +6.4% | WORSE |
| ne_flow/12-23 | 512 | 11.16 | 10.30 | +8.3% | WORSE |
| nw_flow/12-23 | 1059 | 11.35 | 10.45 | +8.6% | WORSE |
| sea_breeze/12-23 | 557 | 18.24 | 16.68 | +9.4% | WORSE |
| sea_breeze/24-47 | 1390 | 17.79 | 16.17 | +10.0% | WORSE |
| se_flow/24-47 | 4333 | 16.65 | 15.04 | +10.7% | WORSE |
| se_flow/6-11 | 788 | 12.96 | 11.24 | +15.4% | WORSE |
| calm/24-47 | 1170 | 12.88 | 11.10 | **+16.1%** | WORSE |
| sw_flow/12-23 | 1972 | 12.84 | 10.27 | **+25.0%** | WORSE |
| pre_frontal/24-47 | 2807 | 14.50 | 10.58 | **+37.1%** | WORSE |

## Ship candidate

Narrow chp to `band == "0-5"` only. Kill all `6-11`/`12-23`/`24-47` bands from the live curated table.

Expected effect (weighted by n over post-Lc window):
- 0-5h retained cells: 2,945 rows, chp -30% vs L6 → preserved wins
- 6h+ dropped cells: 20,875 rows, chp +10-37% vs L6 → losses eliminated
- Net user impact: ~10% MAE reduction on ch across 24K weekly obs

## Why the 10-day digest tool inflates the numbers

`h_ch_persistence_blend_stage2_vs_l6.py` uses a 10-day window (5d + 5d halves). Recent regime shift (near equinox) amplifies chp's mid-lead misses. Full 66-day window says nw_flow/24-47 is +12.1%; the 10-day says +54.62%. Direction is the same, magnitude is 3-5× exaggerated by the short window.

**Don't act on the 10-day numbers.** Verify against the 66-day view before shipping.

## 7-day watch plan

Day 1 = 2026-09-21. Re-check daily. Ship candidate stays viable if:
- 0-5h cells maintain delta ≤ -5% (chp better) every day
- No 0-5h cell flips WORSE for 2+ consecutive days
- 6h+ cells maintain net WORSE (weighted mean >= +5%)

Earliest ship: 2026-09-28.

## How to apply

Any future chp diagnostic — read this note first for the anchor. Don't re-derive band pattern on 10-day windows. If shipping, narrow to 0-5h, don't try to shore up individual mid-lead cells (they're structurally broken by the persistence-vs-forecast tradeoff at longer lead).

Related: [[project_ch_chp_regression_watch_08_13]] · [[project_chp_midlead_regression_watch]] (original watch, superseded by this narrower diagnosis).
