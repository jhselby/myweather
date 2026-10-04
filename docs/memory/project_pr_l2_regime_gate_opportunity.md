---
name: pr-l2-regime-gate-opportunity
description: "2026-07-29: pooled retro shows 6 WIN cells but halves-verify Jaccard=0.00, 4 FLIP cells — single-window artifact on ~5 days of data. Shadow-wire v0.6.389 is the correct path. Re-cut fresh ~08-12."
metadata: 
  node_type: memory
  type: project
  originSessionId: 73429c93-7451-4383-be7a-18cb78ea6325
  modified: 2026-07-29T13:41:59.071Z
---

# pr L2 Regime-Gate Opportunity (2026-07-29)

Ran `analysis/pr_l2_regime_lead_retro.py` on pre-2026-07-01 pair-log data (rows where `pr_l2 ≠ pr_l1`, i.e., before v0.6.276 disabled apply). Cross-cut is `|err_l1|` (raw) vs `|err_l2|` (L2 τ=12h applied) per `state_obs.regime_synoptic` × lead band, n≥200 floor.

**Result: 6 WIN / 4 flat / 16 L2 LOSES / 6 thin.**

WIN cells:
- sea_breeze / 0-5h — **+26.7%**, n=220
- pre_frontal / 0-5h — **+26.1%**, n=233
- calm / 6-11h — +14.2%, n=396
- ne_flow / 12-23h — +9.2%, n=271
- sea_breeze / 12-23h — +7.2%, n=467
- ne_flow / 24-47h — +3.3%, n=270

LOSS shape:
- nw_flow: LOSES 0-5h, 6-11h, 12-23h (flat 24-47h)
- sw_flow: LOSES all four bands
- se_flow: LOSES 0-5h, 6-11h, 12-23h (flat 24-47h)
- calm: LOSES 0-5h (-30.6%!), 12-23h, 24-47h
- pre_frontal: LOSES 12-23h, 24-47h (WIN at 0-5h)
- sea_breeze: LOSES 24-47h (WIN at 0-5h, 12-23h)

**Physical story (pooled).** L2 helps in onshore / marine / transition regimes where station consensus carries real signal the model lags (sea_breeze at short lead is the cleanest — marine boundary layer). L2 hurts in westerly dry offshore flow (nw / sw / se) where station consensus is likely picking up terrain-induced local pressure gradients that don't apply at the Beverly grid point.

**But halves-verification KILLS the ship-now case (2026-07-29).** Split at row-count median: half A = 06-29 → 07-01 (~10.2k rows, ~3 days), half B = 07-01 → 07-03 (~10.2k rows, ~3 days). **Jaccard(A, B) = 0.00** — zero WIN-cell overlap. 4 cells at n≥200 in both halves FLIP sign:
- nw_flow/0-5h: +16.8% → −24.2% (41-pt swing)
- nw_flow/6-11h: +11.0% → −34.2% (45-pt swing)
- nw_flow/12-23h: +2.5% → −12.4%
- se_flow/12-23h: −11.8% → +7.2%

The two strongest pooled effects (sea_breeze/0-5h +26.7%, pre_frontal/0-5h +26.1%) fail even the "n≥200 in both halves" precondition — sample concentrated on one side of the median, i.e. those wins live inside single weather events. **Pooled effect was fitting ~5 days of specific weather, not stable regime physics.**

Critical correction to earlier read: I estimated "3 weeks of retro data" — actual L2-applied window is **~5 days**. Pipeline started writing per-layer detail around late June; 07-01 killed the L2 apply; the retro corpus is the gap between those two dates. Any pooled read on this window is n-large but time-thin.

**Why 07-01 kill missed this.** Pooled Production number was −2.4%, dominated by n-heavy losing regimes (nw + sw + se together ≈ 12k rows in the losing bands vs ≈2k in the winning cells). Predates:
- Skip-table architecture (v0.6.279, 07-02)
- Regime-gate-first discipline ([[feedback_regime_gate_first]])
- `l2_regime_lead_analysis.py` cross-cut machinery

Same class of mistake as [[feedback_calm_gate_wrong_intervention]] — killing a field-level intervention that wins in specific regime cells because it loses in the pooled average.

**Shadow-wire SHIPPED v0.6.389 (2026-07-29).** `corrected_hourly.py` now computes L2-corrected pressure (K=1, τ from `_load_l2_taus` guardrails) and stamps `corrected_pressure_in_post_l2` directly. `decay_apply.py`'s post-Layer-2 snapshot updated to preserve any pre-written `_post_l2` (general shadow-key improvement — only pr uses it today). **Production unchanged**: `corrected_pressure_in ≡ raw_pressure_in`, `pr_applied` stays `l1`. Deploy verified: at 13:37 UTC first shadow tick showed lead-0 shift = current `bias_pressure_in` = −0.015 inHg; decay tail died out by lead 11.

**Fitter has settled pr τ = 3.0h (was 12.0h default when retro ran).** `_load_l2_taus` adopted the fitted τ (held-out +0.00% vs default at n_test=2,304 — passes guardrail on tie). Shadow-wire is therefore measuring a MILDER L2 than the retro: near-identical effect at short lead (bias applied ~full-strength at lead 0), much weaker at long leads (decay dies faster). Expected effect on fresh re-cut: both retro WIN cells (short-lead: sea_breeze/0-5h, pre_frontal/0-5h) and retro LOSS cells (long-lead: nw_flow/24-47h etc) shrink toward flat. Short-lead cells remain the primary candidates.

Re-cut `analysis/pr_l2_regime_lead_retro.py` on fresh-data window ~08-12 (2 weeks) to confirm short-lead WIN cells reproduce under current regimes with τ=3h. Halves-verified test applies (per [[feedback_pooled_n_time_thin]]).

Related: [[project_antecedent_pattern_generalization]] listed pr as "don't need bias-persistence" — that stance was based on the pooled 07-01 read and needs revisiting in light of this cell-level result.

Script: `analysis/pr_l2_regime_lead_retro.py`
Output: `analysis/output/pr_l2_regime_lead_retro.txt` (2026-07-29 read)
