---
name: project-09-22-ims-vs-xr-q-stage15
description: 09-22 Tue — Stage 1.5 co-axis gate script built for inter_model_spread axis-6 wire. Filters 28 Stage 2 SHIP cells down to 15 survivors after xr_q conditioning. Blocks premature wire; sets up 7-day stability watch.
metadata: 
  node_type: memory
  type: project
  originSessionId: a3b1b523-3714-4fec-a95b-290a3dd60c84
  modified: 2026-09-22T13:20:46.252Z
---

# 09-22 inter_model_spread Stage 1.5 — xr_q co-axis gate

## Why this exists

`h_inter_model_spread_c1_stage2` cleared PROMOTE with 28 SHIP cells across
t/wd/wg/dp/pr/ws (v0.6.593 Stage 0 → v0.6.594 Stage 1 → this Stage 2). Its
Stage 1 orthogonality was tested vs C1a_trans / cluster / pt_mag only —
xr_q (cross_run_spread, live since v0.6.401g) was NOT in the gate.

The two signals promoted the SAME 6 fields under separate halves-stable
tests. Both are difficulty proxies. Wiring both without a per-cell ortho
check risks double-widening confidence bands on the same underlying signal.

## What the gate script does

`analysis/h_inter_model_spread_vs_xr_q_ortho.py` — per SHIP cell:
1. Reconstruct ims = |forecast_l1 − forecast_raw_nbm| per pair-log row.
2. Reconstruct cross-run spread per (field, vt) from multi-run forecast_l1 groups.
3. Field-level xr quintile edges, cell-level ims quartile edges.
4. Bin rows (ims_bin × xr_bin), test ims_Q4/Q1 ratio inside xr_Q1 AND xr_Q5.
5. PASS iff ratio ≥ 1.15 in both xr levels; REDUNDANT iff ratio ≤ 1.05 anywhere.

Output: `analysis/output/h_inter_model_spread_vs_xr_q_ortho.json` with
`ortho_gate_pass` list — the curator will consume this for axis-6 SHIP
gating.

## Day-1 result (2026-09-22)

**15 of 28 SHIP cells cleared xr_q conditioning:**
- All 4 dp bands (ratios 1.9–3.6 inside xr_Q1)
- All 4 h bands (ratios 1.4–4.4 inside xr_Q1)
- t/{6-11h, 24-47h}, wd/24-47h, wg/{6-11h, 12-23h}, ws/24-47h, cc/0-5h

**3 FAIL_REDUND** (xr already captures signal): cc/24-47h, wd/6-11h, wd/12-23h.

**10 THIN**: all 4 ch bands (chronic multi-run vt scarcity for cloud fields),
sr/24-47h, and a handful of MIXED_WEAKs in the 1.05–1.15 gray zone
(wg/{0-5h, 24-47h}, ws/6-11h, cc/{6-11h, 12-23h}).

## Where this stands

- Script is in `analysis/*.py` → auto-picked by `run_digest.sh` each morning.
- **7-day stability watch**: PASS set must stay stable (no cells falling
  out to FAIL/THIN, no new cells appearing) before wiring axis 6.
- Earliest wire: 2026-09-29 (if PASS set stable across 7 days).

## Wire plan when gate clears

1. Extend `c1_confidence_calibration_v2.py` to accumulate `by_ims_q` sub-table
   (parallel to `by_xr_q`) — cell-level quartile edges baked in.
2. Extend `c1_curate_confidence_table_v2.py` to load `ortho_gate_pass` from
   this Stage 1.5 output + emit SHIP verdicts for gate-passing cells only
   (mirrors `_load_xr_ortho_fields` at line 48).
3. Extend `confidence_layer.py` — add `_C1_IMS_CELLS` load parallel to
   `_C1_XR_CELLS`, add `_C1_IMS_BAND_MID` band midpoints, wire lookup into
   the marginals loop. Requires either (a) stamping ims per (field, vt) into
   `weather_data["inter_model_spread"]` upstream, or (b) reading `entry["ims"]`
   directly from the forecast_snapshot loop at the same call site.

Option (a) matches the xr_q pattern exactly. Option (b) is one less
processor file but breaks the pattern.

## How to apply

**Rule** (adds to [[feedback_orthogonality_gate]]): when a new C1 axis
overlaps 6/6 fields with a live incumbent axis, orthogonality must be
tested vs that incumbent AT THE CELL LEVEL before wire, not just against
the axes named in the Stage 1 script's default gate list. The Stage 1
default list is a starting point, not a promotion gate.

**Rule** (adds to [[feedback_no_over_gate]]): 15/28 pass after co-axis
gating is a strong result, not a failure. The 13 gated-out cells are
mostly REDUNDANT (correctly caught) or THIN (data-limited, not a design
flaw). Don't tune the gate looser to recover them.
