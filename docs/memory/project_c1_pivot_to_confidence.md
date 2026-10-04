---
name: project-c1-pivot-to-confidence
description: "2026-06-19 evening session — built backtest/replay_conditional.py framework, killed bias-correction C1 (originally numbered L6), pivoted to confidence-layer framing. Stages 1-3 + Stage 4a (dormant briefing line) shipped 2026-06-19 in v0.6.141/142/143. Gated; Stage 3.5 calibration audit due ~06-26."
metadata: 
  node_type: memory
  type: project
  originSessionId: e7a479cb-0418-4bd9-91ef-19777cc97612
---

## What shipped 2026-06-19 evening

**Framework + audits:**
- `backtest/replay_conditional.py` — sibling of `backtest/replay.py` extending the L1-L4 layer-pick with L5 and C1 evaluation. Streamed multi-config sweeps via `analysis/_cache.py`, dynamic per-cutoff config factories (leakage-free train/test for learned biases), James-Stein shrinkage on regime-bias tables. L5 path matches `simulate_windows.py` (+2.28% framework vs +1.7% simulate_windows on 06-19 cutoff — same sign, within sampling noise).
- `analysis/c1_confidence_calibration.py` — Stage 1 of confidence-layer C1. Measures per-(field, band) MAE on stable vs transition pairs over 14 days. Writes `analysis/output/l6_confidence_premium.json`.

**Production code (gated, deployed):**
- `analysis/c1_curate_confidence_table.py` — Stage 2 curation script. Filters Stage 1 cells by sample floor (n≥1000) and magnitude floor (|premium|≥5%), tags as SHIP/MARGINAL/REVIEW/SKIP, flags outliers contradicting field-dominant direction. 39 cells wired (33 SHIP + 6 MARGINAL); REVIEW (pa 6-11h) and SKIP (16 cells) excluded. Output: `weather_collector/data/c1_confidence_curated.json` (committed, ships with deploy).
- `weather_collector/processors/confidence_layer.py` — Stage 3 stamping. `ENABLED=False` (gated). On each tick, classifies current regime inline, compares to model's currently-predicted regime, stamps `weather_data["confidence"]` with per-cell stable/transition/displayed MAE bands. Does NOT modify forecast values — first non-MAE-reducing layer in stack.
- `js/briefing.js` `renderRegimeStatus()` — Stage 4a dormant UI line under the briefing summary. Gated on `data.confidence.applied`, hidden until ENABLED flips. v0.6.142.
- Debug page Status section refreshed in v0.6.143 — C1 listed under "Gated off — built, not applied" with the post-pivot framing.

**Deployed:** Collector revision deployed 2026-06-20T02:55:19 UTC. First post-deploy tick at 02:57:17 UTC verified `confidence` stamped on payload, `applied=False`, 39 cells loaded, `in_transition=False` (calm night). Frontend v0.6.142/143 pushed to GitHub Pages — dormant line invisible to users.

## C1 bias-correction verdict: DEAD

The premise "transition pairs are wronger; learn a bias per (rfc, rob) cell and subtract it" was tested across multiple formulations and ruled out.

**Why:** Bias estimates are noisy point estimates of a non-stationary process. Sample variance is high, target drifts week-to-week, subtraction is too aggressive.

**Formulations tested (all on leakage-free per-cutoff methodology, 7 cutoffs × 7-day windows):**
- `l1_fallback` blend ∈ {0.0, 0.5, 0.75, 0.9, 1.0}: dead for ws/wg/t (L3 too valuable to revert). Marginal +1.07% mean on dp at blend=0.75 across 6/7 cutoffs — only surviving bias-correction candidate, below 3% ship threshold.
- `regime_bias` non-band: dead. Mean -2.88% on dp, -2.96% on wg.
- `regime_bias` band-aware (key = (field, rfc, rob, band)): apparent +1.80% win on ws single-window turned out to be train/test leakage. Leakage-free version: -1.46% mean across 7 cutoffs (2/7 wins).
- `regime_bias` shrinkage k ∈ {0, 30, 100, 300}: shrinkage helps mean improvement asymptote toward zero but never crosses to ship-worthy. k=300 best at +0.18% mean (4/7 wins) — barely positive because shrinkage neutralizes the bias toward no-op.

**Why:** The transition bias structure exists (R6 audit confirmed +10-85% transition penalty as a real measurement) but isn't predictable enough at the (rfc, rob) granularity to subtract.

## C1 pivot: confidence-layer framing

**New premise:** the transition penalty is uncorrectable as a point adjustment; the right response is to widen (or narrow) the displayed uncertainty band on transition hours, not move the forecast value.

This is a category change: every existing L-class layer (L1-L5) is an MAE-reducer; C1 is the first non-MAE output. R0 audit table's "is this layer earning its keep?" question doesn't apply — calibration replaces MAE-delta as the verdict metric.

**Stage 1 calibration is complete.** Per-(field, band) transition uncertainty premium published to `analysis/output/l6_confidence_premium.json`. Key findings:
- Wind fields (wd/ws/wg) widen +10 to +66% on transitions
- Temperature widens +10-15% at mid-bands
- Precip amount widens +57 to +135%
- Cloud cover/low/mid/high NARROW on transitions (model paradoxically more accurate — physically intuitive when fronts impose cloud structure)
- Precip prob narrows -8 to -40%
- Two-way calibration adjustment, not just widening

**Why:** Physically meaningful direction structure, sample-rich (thousands per cell), stable across 14d. Validates the hypothesis as worth promoting to Stage 2.

## Methodology lesson: train/test leakage

The framework's per-cutoff stability test originally used ONE bias table built relative to "now," then scored against 7 cutoffs. Older cutoffs had test windows overlapping the training window — leakage. The +12.7% peak on the 06-14 cutoff was contaminated by ~7 days of training-window overlap.

**Fix:** `evaluate_configs_per_cutoff_dynamic` with `config_factories(cutoff_date)` callables. Each cutoff builds its own bias table strictly older than that cutoff's test window. Cost: 7 extra cache reads per run (~10s).

**Lesson:** any learned-bias C1 audit requires per-cutoff training tables. The framework now enforces this; bake it into the C1 stage-2 audit script.

## Update 2026-06-24 — v3 (4-axis) live; Stage 4 audit infra built

**v3 calibration adds C1f (precip_fc > 0).** `analysis/c1_confidence_calibration_v2.py` extended to add a 4th axis — `state_fc.precip_in > 0 → "p1" else "p0"`. `weather_collector/processors/confidence_layer.py` updated to compute per-band c1f live from `hourly.precipitation` across each band's lead window. The `axis_key` is now `"Q::pt::trans::c1f"`. Curated v3 table regenerated on 14-day window (1.29M pairs, 296,898 multi-axis pairs joined): **296 SHIP / 42 MARGINAL / 1048 SKIP across 39 axis-keys**. Top SHIP-bearing keys: `Q23::rising::transition::p0` (43), `Q23::rising::stable::p0` (41), `Q1::rising::transition::p0` (41). p1 cells are sparser by construction (precip_fc>0 is ~5-10% prior) — most SKIP on sample floor; will fill as more rain-regime data accumulates. v0.6.215.

**Stage 4 audit infrastructure built.** `analysis/c1_stage4_audit.py` lands the Stage 4 UI-readiness gate Joe deferred when ENABLED first stayed False. Handles legacy (transition × stable) and multi-axis (Q × pt × trans × c1f) views. First read 2026-06-24: legacy NOT READY (precip drag), multi-axis DEFERRED to ~2026-07-04 (cluster_spread retention is only 4 days currently). See [[project-stage4-audit]] for the full structure. v0.6.216.

## What's next for C1 (future sessions)

- **Stage 3.5 calibration audit (~2026-06-26):** build `analysis/c1_calibration_audit.py` that consumes 7+ days of stamped `weather_data.confidence` snapshots from GCS, computes per-(field, band) observed-vs-claimed band containment, surfaces calibration error. Success metric: does the claimed band contain truth at the claimed rate? NOT MAE delta. Output feeds the ENABLED-flip decision.
- **Flip `confidence_layer.ENABLED=True`** after calibration passes. Single-line change. Stage 4a briefing line lights up automatically (gated on `data.confidence.applied`); no frontend coordination needed.
- **Stage 4b: per-field band display in cards.** UX design work. UX decision: do users see "± X" brackets always, or only when meaningfully different from stable? Defer until 4a has been live for a few days and we know what users actually want.
- **Per-hour regime classification** (refinement of Stage 3 detection): current detection compares the model's current-prediction regime against observed; transition treatment applies to ALL forecast hours uniformly. More accurate would be per-hour classification of model state (`classify_synoptic_regime()` on each hourly forecast point). Reserved for after calibration confirms the simple version is honest.

## Open architectural decision (resolved 2026-06-19)

Debug page's Status section updated in v0.6.143 to reflect C1's post-pivot framing: listed under "Gated off — built, not applied" alongside L5, with the explicit "first non-MAE-reducing layer" framing. R6 audit kept running (free). No retirement.

The 06-22 walk-forward L3/L4 re-run #2 framing is unchanged and unaffected by C1 work.

## Surviving bias-correction candidate (low priority)

- **dp `l1_fallback` blend=0.75** — ~+1% mean across 7 cutoffs, leakage-free. Below 3% ship threshold but stable. Could ship as a tiny improvement OR could fold into confidence-layer (transition pairs widen dp band, no value change). Decide alongside Stage 2.

## Update 2026-06-29 — C1d candidate killed

**C1d (KBOS-vs-KBVY cloud disagreement) was proposed, built, smoke-tested, and killed within 48h.**

- 2026-06-27 v0.6.247: infrastructure shipped — `cloud_obs_blend.py` stamps `derived.cloud_inter_source_sigma` at L2 blend time; `forecast_snapshot.py` and `forecast_error_log.py` carry it onto each pair row. `analysis/h_cloud_disagreement.py` runs the smoke test.
- 2026-06-28: smoke test verdict **SMOKE_ALIVE** after only ~24h of post-wiring rows — much faster than the expected ~7d. At least one (field, band) showed Q4-σ MAE ≥1.2x Q1-σ MAE.
- 2026-06-29 v0.6.256: `analysis/h_cloud_disagreement_orthogonality.py` ran. Verdict: **KILL C1d**. Holding C1a (transition) fixed, the σ_HIGH/σ_LOW MAE ratio inverts to <1.0 in 3 of 4 (field, band) cells that cleared the n≥100 floor. The σ signal was the transition signal C1a already encodes. C1e check was insufficient (n=0 cells) — could refine with more data but the C1a redundancy is decisive.

**Lesson:** SMOKE_ALIVE alone is not enough to promote. Always run the orthogonality check against existing C1 axes before treating a candidate as worth productionizing. Same finding as C1g (killed earlier by orthogonality vs C1f + cc-saturation). See [[feedback-orthogonality-gate]].

**Active C1 axes (as of 2026-06-29):**
- C1a (regime-transition): live
- C1e (hours-since-front): promoted 2026-06-26
- C1f (precip_fc > 0): promoted 2026-06-24
- C1g (cc-saturation): KILLED 2026-06-24
- C1d (KBOS-vs-KBVY σ): KILLED 2026-06-29
- pre-frontal (hu<24h): PROMOTED 2026-06-27 per `h_pre_front_orthogonality` (likely becomes C1h or merges with C1e bidirectionally — pending naming)
- cluster_spread: shipped as persistent logger 2026-06-19; multi-axis curated wiring blocked on v2 multi-axis Stage 4 audit (~2026-07-04 first eligible)

`confidence_layer.ENABLED` remains False. Latest calibration audit (2026-06-29 local re-curate) moved pass rate 47.92% → 61.36% — still below the 75% threshold for ENABLED-flip.

Related: [[project-correction-stack]], [[project-l5-trajectory]], [[feedback-hypothesis-promotion-pipeline]], [[feedback-whitelist-promotion-gate]], [[feedback-orthogonality-gate]], [[feedback-smoke-alive-then-orthogonality]], [[project-06-18-session]].
