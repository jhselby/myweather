---
name: chp-midlead-regression-watch
description: "chp 14-day watch day 3 (2026-07-21) surfaced a mid-lead 6-20h regression vs Lc. **2026-07-27 v0.6.382r evening re-check with pre-built `analysis/h_chp_midlead_regression.py`: FIRES ESCALATE.** Lc alone beats chp at every 6-20h lead (n=176-186 per lead). Six leads (10-15h) exceed +20% trigger; peak lead 12 = +30.1% (chp MAE 16.37 vs L6 MAE 12.59). Aggregate persistence-skill Δ ≈ −1.03 was masking this because chp still wins big at 1-5h — pooled reading hides the shape. Not shipped yet — Joe's call whether to escalate immediately (rebuild h_ch_persistence_blend_stage2.py against forecast_l6 baseline, re-derive SHIP/SKIP, demote mid-lead cells) or wait for tomorrow's digest confirmation."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0a14e1f9-f87a-464e-846e-dcdd5c525ad4
  modified: 2026-07-27T23:52:21.074Z
---

# chp mid-lead regression watch — 2026-07-21 day 3/14

## The finding

Pulled per-lead chp vs Lc MAE from live `time_series_diagnostic.json` on
2026-07-21 (day 3 of chp 14-day post-ship watch, ship 07-19 v0.6.358).
Watchable per-lead as of v0.6.369 attribution wiring.

| Lead range | Sample n_chp | chp vs Lc |
|------------|-------------|-----------|
| 0 | 50 | +11% (chp slightly worse) |
| 1-5 | 45-49 | **−77% → −6%** (chp winning as designed) |
| 6-11 | 39-44 | +14% → +47% (chp worse) |
| 12-20 | 30-38 | +21% → +53% (chp worse — peak +53% at lead 12) |
| 24-47 | 3-25 | Too thin to trust |

**Short-lead 1-5h chp holds day-2 reads:** lead 1 = 3.59 vs Lc 15.57
(−77%) matches day-2's −81%; lead 2 = 6.29 vs 12.94 (−51%) matches
day-2's −56%. Design intent working there.

**Mid-lead 6-20h regression is new signal.** Day-2 reads only reported
leads 1-2. This band has enough sample (n=30-45) that noise is not
the obvious explanation.

## Suspected cause

chp's Stage 2 SHIP-set was measured against L4 as the baseline (that's
what `h_ch_persistence_blend_stage2.py` computes). Lc landed 07-17;
ch persistence gate landed 07-19 — two days after. So the Stage 2 read
that promoted 27 SHIP cells was comparing chp-vs-L4, not chp-vs-Lc.

Post-flip, chp runs AFTER Lc in the pipeline (per `collector.py:535-544`
comment: "Runs AFTER Lc so persistence overwrites L4+Lc where the gate
fires; Lc's shift was fit against L4 and would re-introduce bias if
applied on top of persistence"). On SHIP cells, chp REPLACES the Lc-corrected
value with pure persistence-of-obs. That's the design.

But the Stage 2 SHIP-set was picked as "chp beats L4 on this cell." If
Lc improves L4 by more than chp does on that same cell (which appears
to happen at mid-lead), then chp SHIPPING there makes ch WORSE than
just letting Lc do the work.

Frontal cells are hardcoded to fall back to L4 in the gate (per Stage
2 halves-checked SKIP). Similar SKIP logic may need to apply to any
(regime × lead_band) where Lc alone outperforms chp.

## Trigger conditions for action

**Day 7 (2026-07-25) re-check:**

1. Re-pull `time_series_diagnostic.json` and rebuild the per-lead table.
2. If mid-lead 6-20h chp-vs-Lc gap **persists at ≥ +20% with n ≥ 100 per lead**,
   escalate to Stage 2 SHIP-set re-verification.

**Escalation path:**

1. Rebuild `h_ch_persistence_blend_stage2.py` with `forecast_l6` (Lc-corrected)
   as the baseline instead of `forecast_l4`. Re-derive SHIP/SKIP verdicts per
   cell.
2. Cross-check against production Lc-in-stack windows using
   `production_whatif`-style measurement (per [[feedback_measure_against_live_stack_baseline]]
   — the divergence-report LSR bug fix pattern applies here).
3. If cells at mid-lead flip SHIP → SKIP under the corrected baseline,
   update `ch_persistence_gate_curated.json` and let the next Stage 2
   run promote naturally. **Do not** demote cells by hand — regime-gate-first
   per [[feedback_regime_gate_first]] means Stage 2 owns the decision.
4. Expected flip magnitude: mid-lead SHIP cells → SKIP; short-lead SHIP
   cells stay SHIP. Net: chp keeps its 1-5h wins, loses the mid-lead
   participation.

**Not a stop-the-line trigger yet.** Watch trigger per
[[project_ch_persistence_gate_ship]] is "chp series drifting TOWARD Lc"
— today's short-lead reads are STABLE vs day 2, not drifting. The
mid-lead regression is a design gap, not a drift alarm.

## 2026-07-23 note — persistence-skill Prod delta is a lagging indicator

Digest AM showed ch Prod skill −1.32 vs L4 −0.28 (Δ −1.04). This is
NOT a new alarm — `h_persistence_skill.py` scans the full pair log
with no date filter, so ~4/30 days of post-chp-flip data are diluted
by pre-flip Lc-only rows. The Δ −1.04 reflects **Lc's damage to ch
pooled across all regimes/leads pre-flip** and confirms the "Lc hurts
ch overall" premise from the escalation path above. As pair log ages
out pre-07-19 rows over the next 2-3 weeks, ch Prod skill should
climb toward the h_ch_persistence_blend estimate (−29% MAE from
routing to persistence-of-obs).

For the actual live-stack chp signal, keep watching `time_series_diagnostic.json`
per-lead — that's the post-07-19-only view. Persistence-skill Δ is a
30-day rolling summary, not a live signal.

## 2026-07-27 v0.6.382r evening — ESCALATE

Pre-built `analysis/h_chp_midlead_regression.py` ahead of tomorrow's Calendar conditional (aggregate persistence-skill Δ outside [−1.2, −0.7]). Ran against live pair log — result is worse than the 07-21 day-3 read that opened this watch.

**Post-2026-07-20 (chp attribution wiring) ch pairs at lead 6-20h, n=2,735:**

| lead | n | MAE_l6 | MAE_chp | Δ% | winner |
|---:|---:|---:|---:|---:|:---|
| 6 | 186 | 12.898 | 13.570 | +5.2% | l6 |
| 7 | 186 | 13.441 | 15.247 | +13.4% | l6 |
| 8 | 186 | 12.968 | 15.360 | +18.4% | l6 |
| 9 | 186 | 12.946 | 15.134 | +16.9% | l6 |
| **10** | **186** | **13.032** | **15.828** | **+21.5%** | **l6** ⚠ |
| **11** | **185** | **12.697** | **15.968** | **+25.8%** | **l6** ⚠ |
| **12** | **184** | **12.587** | **16.370** | **+30.1%** | **l6** ⚠ |
| **13** | **183** | **12.787** | **16.628** | **+30.0%** | **l6** ⚠ |
| **14** | **182** | **12.791** | **15.621** | **+22.1%** | **l6** ⚠ |
| **15** | **181** | **13.160** | **15.801** | **+20.1%** | **l6** ⚠ |
| 16 | 180 | 13.322 | 15.350 | +15.2% | l6 |
| 17 | 179 | 13.520 | 15.022 | +11.1% | l6 |
| 18 | 178 | 13.517 | 14.427 | +6.7% | l6 |
| 19 | 177 | 13.107 | 14.090 | +7.5% | l6 |
| 20 | 176 | 13.000 | 13.312 | +2.4% | l6 |

Six leads (10-15h) fire ESCALATE per the +20% / n≥100 gate. Lc wins at every lead in the 6-20h band. Escalation playbook next:

1. Rebuild `h_ch_persistence_blend_stage2.py` with `forecast_l6` baseline (currently uses `forecast_l4`). Re-derive per-cell SHIP/SKIP verdicts.
2. Cross-check against live-stack via production_whatif per [[feedback_measure_against_live_stack_baseline]].
3. Update `weather_collector/data/ch_persistence_gate_curated.json`. Cells that flip SHIP → SKIP under L6 baseline get demoted; chp keeps 1-5h wins, loses mid-lead participation.
4. Expected: current 27 SHIP cells → ~15-20 SHIP cells (mid-lead 6-20h cells drop out).

**Not shipped tonight** because (a) I ran the per-lead script ahead of the aggregate-Δ trigger — should confirm tomorrow's digest shows aggregate Δ still moving, or explicitly override the aggregate gate with the direct per-lead evidence; (b) this is a live-layer change that requires the full 7-day / 2-tool live-layer change gate per Joe's process; (c) tomorrow's digest is the natural confirmation point.

## 2026-07-27 v0.6.382s — Stage 2 REBUILT vs L6 baseline

Same evening, followed the escalation playbook. Built `analysis/h_ch_persistence_blend_stage2_vs_l6.py` (forked from the shipped Stage 2 so the live one stays authoritative). Uses `forecast_l6` as baseline instead of `forecast_l4`; post-Lc-flip window only (2026-07-17 → 2026-07-27, 10 days); relaxed MIN_N_CELL from 200 → 100 for the tighter window.

**Verdict**: chp's honest SHIP set under L6 baseline is **5 real cells + 3 by-design-frontal artifacts = 8 total** (vs 28 currently live).

**Real SHIP under L6:**

| regime | band | n | L6 MAE | chp MAE | Δ% |
|---|---:|---:|---:|---:|---:|
| calm | 0-5 | 139 | 11.94 | 3.54 | −70% |
| pre_frontal | 0-5 | 196 | 15.64 | 9.27 | −41% |
| sw_flow | 0-5 | 195 | 13.29 | 9.24 | −30% |
| se_flow | 0-5 | 195 | 14.13 | 10.44 | −26% |
| ne_flow | 6-11 | 122 | 10.89 | 9.07 | −17% |

**11 live cells flip → SKIP** (chp materially loses vs Lc):
- pre_frontal 6-11 (+11%), 12-23 (−10% but halves disagree), 24-47 (+32%)
- se_flow 6-11 (+29%), 12-23 (+6%)
- sw_flow 12-23 (+38%), 24-47 (+59%)
- sea_breeze 12-23 (−9% halves disagree), 24-47 (+37%)
- nw_flow 0-5 (−9% halves disagree)
- ne_flow 12-23 (+28%)

**6 live cells go THIN** (n < 100 in the 10-day window): calm/12-23, frontal/0-5 & 6-11 (by design skip), ne_flow/0-5, sea_breeze/0-5 & 6-11.

Preview curated JSON at `weather_collector/data/ch_persistence_gate_curated_vs_l6.json`. Live `ch_persistence_gate_curated.json` UNTOUCHED. Ship path per live-layer change gate: 7 daily reads confirming this shape + 2-tool cross-check + Joe's approval.

**Pattern**: chp's real value is 0-5h short-lead across 4 regimes + ne_flow 6-11h — an 8x tighter footprint than currently live. Mid-lead 6-47h chp is systematic regression the L4-baseline Stage 2 didn't catch because it was measuring against pre-Lc L4, not the live Lc-stack. Same class of bug as [[project_cc_sat_correction]] 07-20 kill.

## Related lessons

- [[feedback_measure_against_live_stack_baseline]] — Stage 2 measured
  against L4 (pre-Lc); post-Lc baseline is different. Same class of bug
  as cc-sat 07-20 kill (measured against pair-log `forecast` which
  carried L1 semantics for cloud fields while Lc was live).
- Applies to any specialist that ships AFTER an established layer: measure
  against the LIVE STACK baseline, not the pre-stack layer.
