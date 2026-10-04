---
name: l3-asymmetric-fc-bin
description: "L3 is a mean-bias subtraction that helps at high fc and hurts at low fc. fc-quartile-conditional skip table extension. Stage 1 07-20; wg 48 SKIP, ws 44 SKIP, cm 0 (gap too small). Needs SKIP_TABLE fc-bin extension in decay_apply.py."
metadata: 
  node_type: memory
  type: project
  originSessionId: d0ce8e13-443e-4221-9625-a6ecbc9e587f
  modified: 2026-07-23T15:43:20.005Z
---

# L3 asymmetric fc-bin skip

Follow-on to `h_asymmetric_l3.py` Stage 0: L3 helps on over-forecast
rows (fc > obs) but hurts on under-forecast rows. wg gap 126.8pp,
ws 65.7pp, cm 14.7pp. The over/under split isn't knowable at forecast
time, but raw fc magnitude IS.

## Hypothesis
L3 is a mean-bias subtraction. When raw fc is above the cell's training
mean, most rows are over-forecasts and L3 helps. Below mean, most rows
are under-forecasts and L3 hurts. Split fc into quartiles per
(regime × band) and skip L3 in low-fc quartiles.

## Stage 1 results (h_l3_asymmetric_stage1.py)

**Confirmed with monotone gradient:**

    wg:  Q1 73%  Q2 45%  Q3 21%  Q4  6% SKIP concentration
    ws:  Q1 52%  Q2 42%  Q3 30%  Q4  9%
    cm:  Q1  0%  Q2  0%  Q3  0%  Q4  0%  (gap too small; no skips)

Total: **92 SKIP cells** across wg + ws.

Biggest SKIPs: sw_flow 24-47 Q1 (wg L2 4.0 → L3 6.2 = +55% worse);
unknown 12-23 Q1 (wg L2 2.0 → L3 4.2 = +112% worse).

## Stage 2 wiring cost
Current `decay_apply.py` SKIP_TABLE keys on `(field, layer) →
[(regime, lo_h, hi_h)]`. Adding fc-bin requires:
1. Load fc_quartile_cuts per (regime, band) from curated JSON
2. At stamp time, bin the raw fc value using cuts
3. Extend `_should_skip()` to accept (regime, band, fc_bin) triple
4. Emit fc_bin dimension in the SKIP_TABLE data structure

Non-trivial refactor. Consider extension to L2 at same time
(t_l2_skip_table_curated found calm 6-11 needs skip; also L2 arch
change needed).

## Next steps
1. Let daily digest accumulate 7-day stability on wg + ws SKIP cell sets.
2. Refactor `decay_apply.py` SKIP_TABLE to support fc_bin dimension.
3. Wire wg + ws (skip cm — no signal).

## 2026-07-23 UPDATE — Stage 2 wiring is DONE

Steps 2+3 above shipped v0.6.366 (wg) and v0.6.370 (ws). decay_apply.py
now has `_load_asymmetric_table` + `_should_skip_asymmetric` + `_fc_bin`
and calls the latter in the L3 apply loop (around decay_apply.py:658).
Both tables are additive — never turn L3 OFF where the existing
regime × band SKIP_TABLE said ON.

Current cell counts (fresh windows 07-23): wg 37 SKIP, ws 25 SKIP (was
48+44 at Stage 1 07-20; some cells demoted to KEEP/MARGIN as data
accumulated). Digest's "Move to Stage 2 wiring" verdict text was stale
and was rewritten in v0.6.375 to "LIVE — table wired since v0.6.366/370".

**No pending Stage 2 work.** Watch the SKIP cell count in digest; if it
drops toward zero or churns wildly, revisit whether the fc-bin gate is
still stable per [[feedback_regime_gate_first]].

## Related
- [[wg_l3_skip_table]] — existing wg L3 skip cells (regime × band only)
- [[ws_l3_long_lead_regression]] — ws L3 nw_flow long-lead already flagged
