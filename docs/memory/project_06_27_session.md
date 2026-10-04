---
name: 06-27-session
description: "Saturday 2026-06-27 morning — digest review, L6 first real Fitter verdict HOLD (−7.88% n=301), Forecast Accuracy chart asymmetry bug found + paired-L4 series shipped v0.6.244. Cluster_spread n=7d re-audit cleared (SHIP persistent logger). L5 trajectory at 6/7 + 12-cycle streak (one ship day to gate)."
metadata: 
  node_type: memory
  type: project
  originSessionId: c67dcba3-13d2-4ccf-bdfd-c7d48c6b16cf
---

## Headline

**Forecast Accuracy chart was lying about L6.** Chart showed L6 ALL=0.73 vs L4 ALL=1.92 (apparent −62% win), but the gate's L6 audit reported HOLD −7.88% on the same morning. Diagnosis: chart's per-layer MAE arrays are accumulated **independently** in `decay_fit.py:629-639` — L4 averages over all ~47,821 7d rows with `error_l4`, L6 only over the ~301 post-`L6_VALID_FROM` rows with `error_l6`. Different row sets per column, plotted side-by-side. The gate's paired-row comparison is the truth.

**Fix shipped v0.6.244 (Joe deployed collector around mid-morning EDT):**
- `decay_fit.py:622-639` — when an `error_l6` row is accumulated for the gate, also bump a parallel `(t, lead, "l4_paired_l6")` counter using the L4 error from the same row.
- `decay_fit.py:1060` — added `"l4_paired_l6"` to the writer loop.
- `corrections_debug.html` LAYER_LINES — new dashed L4-blue entry "Diurnal (paired with L6)", filtered to t-only by `_layersFor`. Doesn't claim the green "user-visible" box (L6 stays rightmost-applied).
- Methodology accordion bullet explains the dashed line + "compare L6 to this, not solid L4."

Self-retires ~2026-07-03 when L6 has full 7d window and paired/unpaired L4 columns converge. Pattern is reusable for the next cold-start layer.

## L6 first verdict

`l6_gate_history.json` first entry: `{verdict: HOLD, improvement_pct: -7.88, n_pairs: 301, fitted_at: 2026-06-27T03:07}`. Not grounds to revert — 7d gate semantics. Watch next 2–3 cycles. The 03:07 sample was short-lead-heavy (only ~12h of post-VALID rows accumulated by then).

## Other reads from this morning's digest

- **L5 trajectory:** 6/7 SHIP days, 0 HOLD, 12-cycle SHIP streak. One ship day to gate-clear. Earliest promotion 06-28 if 03:07 or 15:07 stays SHIP. ([[project-l5-trajectory]] updated.)
- **cluster_spread n=7d re-audit:** SMOKE_ALIVE + SHIP PERSISTENT LOGGER. 9 ORTHOGONAL / 3 CONFOUNDED / 7 REDUNDANT / 1 AMBIGUOUS. Genuinely additive to R6. Next: ship the persistent logger.
- **h_pre_front_orthogonality:** first PROMOTE (16 ortho cells, independent of C1a + C1e). New Stage 2 candidate.
- **h_hsf_orthogonality:** PROMOTE (5 ortho — "ship as C1e axis").
- **h_precip_fc_orthogonality:** PROMOTE (25 ortho).
- **c1_calibration_audit:** HOLD (47.92% pass rate). Re-curate as the script's next-step note says.
- **c1_stage4_audit multi-axis:** still DEFERRED to ~2026-07-04.
- Backlog tunings noted but not done: `decay_tau_tuning` per-field τ, `l2_lead_decay_fit` IMPLEMENT L2 LEAD-DECAY (h +2.5% τ=36h, pr +4.3% τ=12h).

## Lessons preserved

- **Independent per-layer aggregation is dishonest when layers have different deploy ages.** Future new layers will hit this same trap during their first 7 days. The `l4_paired_l6` pattern is the template: emit a same-row-subset baseline column alongside any newly shipped layer, retire it once the layer has a full window. (Could be generalized into the Fitter as a "paired baseline for newly-shipped layers" mode if it happens again.)
- **Trust the gate, not the chart, on layer comparisons** — the gate is paired-row by construction, the chart is per-layer-independent by construction.

## What's still pending

- **Frontend push for v0.6.244** — waits until next Fitter cycle (15:07 EDT or `?fit=1`) populates `per_layer_mae_by_lead.t.l4_paired_l6` in GCS + localhost test of the chart shows the dashed line correctly.

## Related

- [[project-l6-microclimate-correction]] — updated with first verdict + chart-fix history
- [[project-l5-trajectory]] — refreshed to 6/7 + 12-cycle
- [[project-hypothesis-backlog]] — three new ortho PROMOTEs + cluster_spread cleared
- [[project-06-26-session]] — yesterday's marathon; today's chart-fix is the natural follow-on
- [[feedback-debug-page-canon]] — debug page is source of truth; this entry confirms it can also lie if the underlying data shape isn't apples-to-apples
