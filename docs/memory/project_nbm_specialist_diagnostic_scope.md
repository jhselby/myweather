---
name: project-nbm-specialist-diagnostic-scope
description: "Diagnostic scoping memo (09-09) — why do ported NBM specialists (chp_nbm, wdp_nbm, L5_NBM sr, L6_NBM t) mostly fail to earn, and what's the cheapest experiment to distinguish \"NBM error surface is smoother\" from \"NBM error surface has different structure\"? Real finding — L3_NBM + L4_NBM are POOLED (no regime/band dimension), while HRRR L3/L4 are per (regime, band, fc-quartile). That may be the largest untapped lift on the NBM side."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f584257-df4f-41a9-b227-c4bdf632ea0a
  modified: 2026-09-09T14:29:37.698Z
---

# NBM specialist diagnostic scope — 09-09

Reframe of the "clone more HRRR gates" workstream. The right first question isn't which gate to port — it's why so many of the already-ported gates failed, and what the underlying NBM error structure actually looks like.

## What's already ported (I under-stated this earlier)

**Structural ports (v0.6.437 → v0.6.499, 08-19 to 08-26):**
- L2_NBM native math — all 8 fields.
- L3_NBM bias — `{t, ws, wg, h, ch, sr, dp, cc, wd}` fitted; runtime scope `{wg, ch, cc, sr}`.
- L4_NBM diurnal — `{ch}` runtime (cc dropped 09-08).
- L5_NBM solar — `sr` scaffolded.
- L6_NBM Kalman — `t` scaffolded.
- chp_nbm ch persistence gate — inline in forecast_snapshot.
- wdp_nbm wd persistence gate — inline in forecast_snapshot.

**Failure pattern of ported layers:**
- `chp_nbm` — KILLED 09-05 v0.6.551 (sentry HOT, correction dragging Prod below raw).
- `L5_NBM sr` — killed 08-25 v0.6.471 (sentry HOT +238%, walkforward agreed DROP sr).
- `L3_NBM sr, t, ws` — dropped 08-25 v0.6.472 (walkforward DROP; wg kept for cell review).
- `L3_NBM dp` — dropped 08-24 v0.6.465 (pooled bias actively harming users).
- `L3_NBM h` — killed 09-05 v0.6.551 (paired with chp_nbm kill).
- `L4_NBM cc` — dropped 09-08 v0.6.563 (walkforward DROP cc, 30d pooled lift +0.79%).
- `wdp_nbm` — LIVE, but today's walkforward proposes DROP wd.
- `L6_NBM t` — never enabled (blocked on "does NBM L2 double-count waterfront" investigation).

**Score:** 2 net-earning ports (L4_NBM ch, wdp_nbm — and wdp_nbm on notice), 6 killed/dropped, 2 never enabled. That is not a "port everything" success pattern.

## Real finding — L3_NBM and L4_NBM are POOLED

I looked at the curated JSON shapes today. This is the load-bearing gap:

**HRRR L3** (`decay_apply.py` reads `decay_corrections.json`): per `(regime, band, fc-quartile)` **asymmetric additive** with an explicit SKIP_TABLE of cells that regress. 9 regimes × 4 bands × 4 quartiles = 144 cells per field, halves-verified.

**L3_NBM** (`l3_nbm_curated.json`): per-lead pooled — a single scalar bias per (field, lead_h). No regime, no band, no quartile.

```
python -c "import json; d=json.load(open('.../l3_nbm_curated.json')); print(type(d['corrections']['wg']), len(d['corrections']['wg']))"
# <class 'list'> 48   ← 48 lead-hours, single value each
```

**HRRR L4** (`decay_apply.py`): per `(regime, band)` diurnal residual.

**L4_NBM** (`l4_nbm_curated.json`): per hour-of-day pooled — single scalar per (field, hour_local). No regime.

**Implication:** every regime-structured NBM ship needs its correction to survive the fact that L3_NBM has already applied a pooled bias that's optimal on average but wrong in specific regimes. That's why sentry keeps flagging HOT: NBM's L3 correction is over-shooting some regime × band cells and under-shooting others, but no regime-aware gate can fix it after the fact — the bias has already been baked in.

## Two competing hypotheses

**Hypothesis A: NBM's error surface is genuinely smoother than HRRR's.**
NBM is a national blend of multiple deterministic + ensemble sources with post-processing. It arrives already regime-agnostic and less biased than HRRR at the coast. Pooled per-lead correction captures ~all of the fixable bias; there's no residual regime structure worth fitting. Direct-clone gates fail because there's no leverage. Predicted signature: per-regime L3_NBM fit shows held-out MAE within ±1% of pooled.

**Hypothesis B: NBM's error surface has different structure than HRRR's.**
NBM biases exist but along different axes than HRRR — different regime interactions, different diurnal shapes, different lead-time decay curves. Direct clones fail because they're solving on the wrong axis. Predicted signature: per-regime L3_NBM fit shows meaningful held-out MAE lift (≥3% pooled or ≥5% in specific hot regimes) even when the winning cells don't match HRRR's SHIP_TABLE.

**These have very different implications:**
- A → stop porting HRRR gates. Focus on selector + Kalman tuning + minor. NBM cascade is essentially done.
- B → build a native NBM specialist workstream. Stage 0 exploration on NBM residuals, don't port anything.

## Cheapest diagnostic to distinguish

**One-session analysis-only ship: `l3_nbm_fit_by_regime.py`** — fork of `l3_nbm_fit.py` that fits per (regime, band) instead of pooled per-lead. Writes a **preview** JSON, does NOT overwrite runtime. Report:

1. Per-field held-out MAE: pooled vs per-regime, on 7d test window.
2. Halves stability (first 3.5d vs second 3.5d) — required to reject noise.
3. Per-cell win counts vs pooled (how many regime × band cells materially beat pooled).
4. Bias signatures — do NBM cool-side biases in sea_breeze look like HRRR's? Do they concentrate in different lead-bands?

If per-regime beats pooled by ≥3% overall with halves-stable + ≥5 winning cells → hypothesis B confirmed → scope the wire-in as a real workstream.

If it's within ±1% pooled with no cell dominance → hypothesis A confirmed → close the "port more" thread, focus elsewhere.

**Estimated effort:** 1 session, ~120 LOC (clone of l3_nbm_fit.py + regime binning + halves-stable grid search). Analysis-only, no runtime change, no ship pressure.

## Adjacent diagnostics worth doing in the same pass

- **L4_NBM per-regime fit** — same shape at L4 (currently pooled per hour-of-day).
- **NBM residual "regime × hour_local" heatmap** — pure exploration, no fit. Just look at where NBM's post-L3_NBM residual concentrates. If it's in sea_breeze afternoons → sea-breeze specialist. If it's in nw_flow 24-47h → residual-persistence-shape. If it's flat → hypothesis A.
- **NBM raw vs HRRR raw bias direction correlation.** Does the direction of NBM bias match HRRR bias in the same regime? If yes, HRRR gate shapes should transfer (contradicting the fail pattern). If no, direct clones were doomed.

## Related open questions this diagnostic feeds

- **Why is wg corr −11.3% today** on NBM-routed cells (per_field_scoring)? Diagnostic will show whether it's L3_NBM over-correction in specific regimes or systemic.
- **Why is dp corr −8.6%** on NBM-routed cells? dp isn't in L3_NBM_FIELDS runtime (dropped 08-24), so this is L2_NBM + selector-inheriting-t/h-errors. Diagnostic on t + h will illuminate.
- **Should wdp_nbm be dropped?** Walkforward says yes; diagnostic gives the mechanistic explanation.

## What NOT to do until the diagnostic reads

- Do NOT clone `wg_residual` or any other HRRR gate to NBM. Even if HRRR wg_residual eventually clears its walker, the port-and-fail pattern (chp_nbm, L5_NBM sr, L3_NBM sr/t/ws/dp/h, L4_NBM cc) says direct ports fail on NBM.
- Do NOT scope "NBM sea-breeze specialist" from first principles yet. If hypothesis A is right, that's wasted work too. If B is right, the diagnostic will point at which regimes have the residual structure to exploit.
- Do NOT touch runtime NBM cascade config until we know what shape is worth building.

## Timeline

- **Now → 09-11:** wait on walker wire read, don't disturb the signal.
- **09-11 evening:** post-wire attribution read. Selector routing corrects or doesn't.
- **09-12 or 09-13:** run the diagnostic. Session 1 = build `l3_nbm_fit_by_regime.py`, session 2 (probably same day) = interpret + write findings memo.
- **Decision point 09-13:** hypothesis A → close NBM specialist workstream, focus elsewhere. Hypothesis B → scope specific specialist Stage 0 based on diagnostic residual heatmap.

## Related

- [[project_nbm_parallel_pipeline_plan]] — the port plan; doesn't cover this failure pattern
- [[project_nbm_structural_completion_plan]] — largely shipped
- [[project_wg_residual_nbm_scope]] — earlier scope; superseded by this reframe
- [[feedback_measure_before_concluding]] — pattern-match: I was about to recommend cloning based on an inaccurate read of the NBM stack state
- [[project_09_09_digest_watches]] — l3_nbm ADD wd walkforward proposal is now clearer: walkforward is seeing a wd signal that pooled-L3_NBM can't capture; adding wd to L3_NBM_FIELDS just pools it. Real answer is per-regime L3_NBM
