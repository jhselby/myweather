---
name: project-07-01-session
description: "2026-07-01 sprint — 11 versions (v0.6.263 → v0.6.273) across two days. Themes: TODO-driven UX pass on the debug page; Production line concept end-to-end (approximation → per-row real via forecast_snapshot + pair-log stamps + Fitter aggregation → hybrid frontend render); PP Brier native rendering (Fitter emit + auto-swap frontend); C1e (hours-since-front) shipped end-to-end as the 5th multi-axis dimension (curator + collector); CALM_GATE killed as wrong intervention; per-field τ_ws=7 (+6.7% held-out); scorecard banner. Open: L6 warming branch may itself be net-negative (see [[project-l6-warming-branch-watch]]); L5 RETIRE-vs-AGREE unresolved; h→L4 gate 1/7."
metadata: 
  node_type: memory
  type: project
  originSessionId: 56248ef4-af78-48a9-998a-163e8a07965d
---

## What shipped (v0.6.263 → v0.6.273)

Full run in `docs/CHANGELOG.md` and the Since-last-curation block on the debug page. High-level bucketing:

**2026-06-30 evening — big UX pass on `corrections_debug.html`** driven by `Wyman_Cove_Engineering_TODO_Combined.txt`:
- v0.6.263: renames (Status → Engineering updates, triggers → applies); Applicability map intro + Terminology key; Production Stack reframed as Core / Specialists / Confidence; Q/E/D on Upcoming Decisions; L3/L4 + L5 5-block layout; R&D reorg (Diagnostics / Candidates / Experiments); new Archive top-level section.
- v0.6.264: Production line + column on accuracy charts. `_productionLayerKey` picks deepest applied layer per field.
- v0.6.265: dropped `.layer-active` per-column highlighting; Production* marked approximation. Joe's redirect on the "no single applied layer under conditional gates" framing.
- v0.6.266: **CALM_GATE killed as wrong intervention** — see [[feedback-calm-gate-wrong-intervention]]. PP card MAE-vs-Brier disclaimer. KBOS+KBVY cloud blend prose fixed to say hourly[0]-only.

**2026-07-01 — backend + Fitter + curator + frontend swap:**
- v0.6.267: CALM_GATE code removed from `decay_apply.py`. Per-lead Brier for PP emitted from `decay_fit.py` (`per_layer_brier_by_lead.pp`). Analysis: dp L4 regime cross-cut (skip-table case); `h_cloud_bias_persistence.py` HOLD (cc bias doesn't persist past ~3h; residual short-lead Stage 1 candidate spun out).
- v0.6.268: PP card Brier-native frontend with MAE fallback.
- v0.6.269: **Per-row applied-layer stamping** — `forecast_snapshot._derive_applied_layer()` walks L1→L6 arrays, picks deepest layer whose value changed (every gate today is deterministic at forecast time). Copied to pair-log rows. Fitter aggregates `per_layer_mae_by_lead[field].production`.
- v0.6.270: Scorecard banner (Overall / Winning fields / Biggest gain / Biggest regression). C1 curated tables re-run.
- v0.6.271: `TAU_DAYS_BY_FIELD["ws"] = 7` (+6.7% held-out). C1e telemetry stamp.
- v0.6.272: **C1e end-to-end**. v2 curator extended to 5-tuple axis_key with hsf dimension. 840 SHIP / 118 MARGINAL / 1828 SKIP of 2,786 multi-axis cells (up from 619/1,764). C1 calibration audit pp Brier exemption (pass rate 55.81% → 61.54%).
- v0.6.273: Frontend hybrid Production array + canon-page refresh. See [[feedback-hybrid-transition-pattern]].

## Real institutional findings (not in the code)

1. **CALM_GATE was wrong.** ws L3 in the calm regime WINS +15% to +44%; the actual losers are ne_flow + short-lead sea_breeze. fc_ws<3 gate would have skipped L3 exactly where it wins biggest. Codified in [[feedback-calm-gate-wrong-intervention]]. Cross-cut method: [[feedback-regime-lead-band-cross-cut]] predicted this pattern.

2. **L6 warming branch may itself be net-negative.** The 06-30 cooling-branch disable may not be enough. Real per-row Production at short leads (n>25) shows T Production still worse than L2 alone by ~15%. Not enough data to conclude yet — see [[project-l6-warming-branch-watch]].

3. **Cloud bias doesn't persist past ~3h.** `h_cloud_bias_persistence` Stage 0: strong lead-1h persistence (ρ +0.50 to +0.66 across cc/cl/cm/ch), collapses to near-zero/inverted by lead 6h. Rules out full per-lead L2 propagation for the KBOS+KBVY blend; residual Stage 1 candidate for a tight-τ (~2h half-life) short-lead propagation.

4. **dp L4 is a skip-table case, not a wholesale add.** 8 WIN / 9 flat / 15 L4 LOSES / 4 thin. `ne_flow` is the consistent loser on both ws AND dp — confirms the regime axis carries real signal, not noise.

## Design patterns codified

1. **Hybrid transition rendering** — see [[feedback-hybrid-transition-pattern]]. When shipping a backend key that fills over a rolling window, frontend renders real-where-populated + approximation-elsewhere. Coverage-threshold auto-drops the "*" marker per-card.

2. **Per-row deterministic-gate stamping** — every correction gate today is deterministic at forecast-build time (L2/L3/L4 field membership; L5 sun-up threshold; L6 regime + sea-breeze octant; marine layer wd+hour; future skip table by state_fc). The applied-layer for a (field, lead) is exactly the deepest layer whose per-lead array value differs from the previous captured layer. An equality walk through the per-layer snapshot arrays recovers it exactly. If a per-row *observation-side* gate ever ships, this approach breaks and needs a real stamp at correction-application time.

3. **Decision-metric-specific Fitter aggregation** — PP Brier accumulator sits alongside MAE/bias/n, populated only for pp rows. Emitted at `per_layer_brier_by_lead.pp`. Frontend swaps automatically when the key is present. Pattern applies to any future Brier-evaluated field.

4. **Curator axis extension** — Adding a new C1 axis dimension (like C1e / hsf_group) requires: (a) helper that classifies live tick into buckets, (b) curator loop iterates the new axis when building `by_axes` keys, (c) axes metadata declares the labels, (d) collector's `stamp_confidence()` axis_key composition includes the new dimension. Falls back to legacy gracefully when the axis is missing at the tick.

## Open at session end

- **L6 post-fix compression watch** — 07-01 03:07 read at −22.58%. Expected linear to ~0% by 07-07 if the fix worked. Below expected trajectory so far (0.5 pp/day vs expected 3.2 pp/day). Correlates with #2 above.
- **L5 RETIRE-vs-AGREE puzzle** — `simulate_windows` says HOLD across all 7 cutoffs → recommend RETIRE; divergence-report says AGREE. Still unresolved from [[project-06-30-session]].
- **h → L4 gate** — 1/7 cycles. 6 more digest cycles to gate clear. Also run `l4_regime_lead_analysis` on h before flipping.
- **C1 calibration still HOLD** — 61.54% post pp-exempt (up from 47.83%). Genuine drift on cm/ch/sr/cc/pr/t/pa remains. Next: re-audit with new 5-axis curated table active; add a Brier-based drift check for pp.
- **Skip-table architectural commit** — first cells scoped for ws + dp (both LOSES on ne_flow at all bands; both LOSES on short-lead sea_breeze). Real design work; deferred as a dedicated session.
- **Deploy pending** — CHANGELOG catch-up for v0.6.263 → v0.6.273 (Joe explicitly flagged as "not now" earlier; separate commit when ready).

## Lesson preserved

Real per-row data always exposes what the population-level approximation was hiding — even when the approximation was designed with the same target semantics. See T's Production numbers landing 15–40% BETTER than the L6 approximation at short leads on day 1 of stamping; the approximation was pessimistic because it treated one-in-three L6-fired rows as if every row got L6. When shipping a new aggregation that will replace an approximation, plan for a transition period; don't assume you know how the two compare.
