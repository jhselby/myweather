"""Stage 0 — Cloud saturation-unbiasing (backlog item #1 from 2026-06-24).

Hypothesis: at forecast cloud-cover ≥ 95%, all four cloud fields (cc, cl, cm, ch)
show large negative bias against observations (model too confident in overcast).
h_cloud_floor_ceiling reads 2026-06-23 showed cl 95-100% at −57.5pp, direction
stable across the two 06-23/06-24 reads. Genuinely new architecture — no existing
correction layer conditions on forecast VALUE (Lc conditions on lead, L4 on regime,
chp on state, C1 on axes; none on the forecast-side saturation bin).

Ship shape (if it clears):
  Regime-agnostic additive shift applied when fc_X ≥ SATURATION_THRESHOLD and
  the historical (fc_X, obs_X) pair on the same site+season shows a stable
  negative bias. Two candidate mechanisms —
    (a) Bin-conditioned additive: fc_X_corrected = fc_X − mean_bias_at(fc_bin).
    (b) Sigmoid-taper on the top decile: unbiasing weight tapers 0→1 across
        fc_X 90→100 to avoid a hard step at the threshold.

Stage 0 gate (this script should implement, not yet):
  1. Load pair log, filter to rows where fc_X ≥ 90 for X in (cc, cl, cm, ch).
  2. Bin by fc value (90-95, 95-100) and compute (obs_mean, fc_mean, gap).
  3. For each (field, bin, band), report: n, gap_pp, direction-stability across
     two chronological halves.
  4. Verdict: PROMOTE if |gap_pp| ≥ 20 AND halves-stable AND n ≥ 500 in ≥1 cell.

Blockers before Stage 1:
  • Cross-check against L4_FIELDS — if a live L4 already fires in fc-high bins,
    quantify whether L4 is doing this work already. If yes, no new layer.
  • Orthogonality vs C1 axes — is the gap concentrated in transition rows
    (C1a already amplifies confidence there) or is it independent?
  • Sample floor at fc ≥ 95 for cl and ch specifically; cm and cc are more
    frequently populated in overcast.

References:
  • analysis/h_cloud_floor_ceiling.py — the aggregate detector this Stage 0 splits.
  • project_hypothesis_backlog #1 — the original spec.
  • feedback_orthogonality_gate — SMOKE_ALIVE → orthogonality before wire.
"""

VERDICT = "STAGE 0 SCAFFOLDING — cloud-saturation-bias mechanism-test pending. See docstring for spec. Backlog item #1, direction-stable across 06-23/06-24 reads; needs current-window Stage 0 fit against pair log."
print(VERDICT)
