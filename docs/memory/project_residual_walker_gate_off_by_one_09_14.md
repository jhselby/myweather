---
name: residual-walker-gate-off-by-one-09-14
description: "09-14 root-cause: shared _residual_persistence_walker.py cutoff was off by one, producing an 8-day window for a 7-day gate. Line 149's `n_seen == GATE_WINDOW_DAYS` never fired. All three residual walkers (wg/dp/h) had 0 clearances since inception. Fix: cutoff = now - (GATE_WINDOW_DAYS - 1). Post-fix: 16 wg cells + 7 h cells + 6 dp cells cleared. No runtime change today — all three processors ENABLED=False."
metadata: 
  node_type: memory
  type: project
  originSessionId: c656ec98-2726-4d09-8e93-674722e5843d
  modified: 2026-09-14T14:11:17.502Z
---

# Residual-persistence walker gate off-by-one — 09-14 fix

## The bug

`analysis/_residual_persistence_walker.py:117` had:

```python
cutoff_win = (datetime.now() - timedelta(days=GATE_WINDOW_DAYS)).strftime("%Y-%m-%d")
```

With `GATE_WINDOW_DAYS = 7` and today=09-14, cutoff = 09-07. Filter `date >= "2026-09-07"` includes 09-07 through 09-14 = **8 dates**. Line 149 checks:

```python
cleared = (n_seen == GATE_WINDOW_DAYS and n_pos == GATE_WINDOW_DAYS)
```

With 8 days seen, `8 == 7` is False. Cell never clears even when every one of the 8 days is SHIP.

## Symptom

Since the shared harness landed (v0.6.532 08-31 for h, earlier for wg + dp), **zero cells cleared across any of the three residual-persistence walkers.** Memory index had wg listed as "live via shared harness" — **wrong; it was shadow the entire time (ENABLED=False)**.

Cells kept "flipping in window" was the surface signal we saw; the deeper issue was that even non-flipped, uniformly SHIP cells never cleared either. sw_flow/12-23 for h: `days_seen=8, days_positive=8, days_ship=8, flipped_in_window=false, cleared_for_wire=false`. That combination is the fingerprint.

## Fix (v0.6.613)

```python
cutoff_win = (datetime.now() - timedelta(days=GATE_WINDOW_DAYS - 1)).strftime("%Y-%m-%d")
```

Window now contains exactly 7 dates (today + 6 prior). `n_seen == GATE_WINDOW_DAYS` fires when 7 days have been seen and populated.

## Post-fix walker output (09-14)

| Field | cleared | flipped | processor ENABLED |
|---|---|---|---|
| wg | 16 | 2 | False |
| dp | 6 | 6 | False |
| h | 7 | 7 | False |

wg cleared cells: `frontal/24-47`, `ne_flow/24-47`, `ne_flow/6-11`, `nw_flow/0-5`, `nw_flow/6-11`, `nw_flow/12-23`, `nw_flow/24-47`, `pre_frontal/6-11`, `pre_frontal/12-23`, `pre_frontal/24-47`, `se_flow/0-5`, `se_flow/6-11`, `se_flow/24-47`, `sw_flow/0-5`, `sw_flow/6-11`, `sw_flow/12-23`.

h cleared cells: `nw_flow/6-11`, `nw_flow/12-23`, `nw_flow/24-47`, `pre_frontal/24-47`, `se_flow/12-23`, `sw_flow/12-23`, `sw_flow/24-47`.

dp cleared cells: `nw_flow/6-11`, `nw_flow/12-23`, `nw_flow/24-47`, `sw_flow/6-11`, `sw_flow/12-23`, `sw_flow/24-47`.

## Runtime impact today

**Zero.** All three processors are ENABLED=False. The fix only makes the walker report ship-eligibility correctly.

Follow-up decisions (separate ships, not today):

- **wg** — 16 cleared cells is a very strong ship signal. Stage 2 preview shipped 07-14. Consider flipping ENABLED=True on wg_residual_persistence.py after one more week of stability.
- **h** — 7 cleared cells. Processor pre-staged 08-31 v0.6.530 with all bugfixes baked in. Same consideration as wg.
- **dp** — do not flip per [[project_dp_is_derived_no_dp_work]]. dp is Magnus(t, h); dp-side correction routes signal to h instead.

## Why nobody caught this earlier

- Digest reports "0 cells cleared" as normal walker output; nothing raised it as anomalous.
- Everyone assumed cells were legitimately flipping and the mechanism was working conservatively.
- Post-ship watches for wg / dp / h all said "waiting on walker cell clearance" — treated as normal churn.
- Memory index had wg listed as "live via shared harness" — that was aspiration, not reality.

## How to apply

- Any walker built on this shared harness is subject to the same off-by-one class of bug. If ever writing another `days_ago` cutoff calculation for a "last N days" rule, sanity-check: window filter `>= today - (N-1)` gives N days, `>= today - N` gives N+1.
- On next digest read, verify the number of days_in_window matches GATE_WINDOW_DAYS. If they mismatch by one, the gate is broken.

## Second walker with same bug (v0.6.614)

`analysis/h_chp_cell_gate.py:137` had the same cutoff bug (`now - GATE_WINDOW_DAYS`). Symptom in yesterday's digest: "HOLD — no cell has cleared the 7-day all-lose gate today. Walker at day 8/7 distinct dates." The "8/7" is the fingerprint.

Post-fix: **11 cells cleared** (4 overlap _CELL_SKIP; 7 net-new dynamic suppressions).

Net-new dynamic suppressions (chp losing 7d straight, not in _CELL_SKIP):
- ne_flow/6-11, ne_flow/12-23, ne_flow/24-47
- nw_flow/6-11, nw_flow/24-47
- pre_frontal/6-11
- se_flow/12-23

Runtime impact today: **zero.** `CHP_CELL_GATE_ENABLED = False` in `ch_persistence_gate.py`. The dynamic gate is shadow-only.

Follow-up (not today): watch fresh 7-day post-fix accumulation. If the 7 net-new dynamic-suppression cells stay in the clear-list through ~2026-09-21, consider flipping `CHP_CELL_GATE_ENABLED=True`. This would let the dynamic gate correctly suppress the 7 cells that are consistently losing to L6.

**Only-two-walker-audit:** `_residual_persistence_walker.py` and `h_chp_cell_gate.py` had the bug. Other walkers (`h_cc_blend_formula_stage1.py`, `h_frontal_t_bias_stage0.py`) use the tolerant `>= GATE_WINDOW_DAYS` check and are unaffected.

## Related

- [[feedback_measure_before_concluding]] — bug went undetected because we treated walker output as ground truth without checking whether the mechanism was even firing correctly.
- [[project_h_residual_persistence_attribution_08_30]] — Stage 1 harness fixes from v0.6.520-522 exposed 3 real bugs via `/code-review high`. Same class of issue (mechanism silently mis-firing) but a different place.
- Stage 3 processors: `weather_collector/processors/h_residual_persistence.py`, `wg_residual_persistence.py`, `dp_residual_persistence.py`.
