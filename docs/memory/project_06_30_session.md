---
name: project-06-30-session
description: "2026-06-30 marathon — three substantive ships (L6 surgical cooling-branch disable v0.6.259, applicability map plumbing + Section D rendering v0.6.260, walkforward validator bugfix v0.6.262) plus a big editorial cleanup of corrections_debug.html. Net pipeline state: L6 warming-only; applicability map block live in weather_data.json + on debug page; walkforward correctly surfaces cc-stays-in-L4 + h-as-new-L4-candidate. Frontend at v0.6.262, collector at v0.6.260."
metadata: 
  node_type: memory
  type: project
  originSessionId: 76252fe3-ab5d-4a76-8031-bc90764206fd
---

## What shipped

**v0.6.259 — L6 cooling branch disabled.** `analysis/l6_l2_double_counting.py` rejected the "L2 already pulls toward cove → L6 double-counts" hypothesis (L2 only erases 3.7% of L1's MAE on cove rows — barely moves the needle). Real cause: L1 is structurally cold ~2.25 °F at the cove; L6's sb_off offshore-hour cooling branch was doubling MAE on cooling rows (Δ ≤ −2 °F bucket: 3.52 → 6.16, −74.9%). Surgical fix: `compute_cove_correction()` returns 0.0 in the sb_off branch, sea-breeze warming branch (sb_active, S/SE/SW) retained. Independently confirmed by `r5_cove_analysis`: warming gradient PASS (+1.80°F), cooling gradient FAIL (−0.54°F). See [[project-l6-l2-double-counting-hypothesis]] for the full diagnostic.

**v0.6.260 — Applicability map shipped end-to-end.** Each correction module (`decay_apply`, `solar_correction`, `cove_correction`, `confidence_layer`) exposes `describe_applicability()`. Collector concatenates the union into `weather_data["applicability_map"]` each tick. Debug page reads it in a new "Applicability map — what corrections trigger, and why" section. Schema example at `weather_collector/data/applicability_map_schema.json`. Steps 1–5 of [[project-applicability-map-design]] done; steps 6 (per-layer filtered slices) + 7 (A/B/C section reorg) deferred — the category badges in the global map carry the distinction.

**v0.6.262 — walk-forward L3/L4 validator bugfix + page cleanup.**
- Validator bug: old logic gated L4 evaluation on L3 earning its keep first. For fields not in `L3_FIELDS` (cc, t, dp, h, ws, wg, sr, pr, pa), `forecast_l3 == forecast_l2` by construction → L3 trivially didn't beat the 2% threshold → L4 was never scored. Validator was recommending `off_off` for nearly every field, including cc where L4 beats baseline by 9% at every lead band. Fix: evaluate L3 and L4 INDEPENDENTLY; added `off_on` as a valid state (matches actual production for fields like cc that are in `L4_FIELDS` but not `L3_FIELDS`). Re-run produces correct recommendations: `L3_ENABLED = {ch, cm}`, `L4_ENABLED = {h, cc, ch}`.
- Page cleanup: Status section compacted (~80 → ~30 lines); L6 section now leads with current state ("warming branch only"); R2 renderer tags already-addressed fields and picks "Top actionable opportunity" past them; G1 cleared of R5 (retired) + L5 (shipped); S1 scope tightened to field-membership only; backlog stripped of killed entries (live only in Retired now); shipped entries compacted to one-liners; chart legend color bug fixed (`LAYER_LINES[i]` indexing broke when L5/L6 filtered out).

## Real signals surfaced by the walkforward fix

1. **cc stays in L4** — the "drop-cc gate" the divergence-report was building toward was a phantom from the bug. Chart was right all along.
2. **h is a new L4 candidate** — +5.2% MAE win (6.39 → 6.05). Genuine. Apply standard 2-read gate before flipping `L4_FIELDS`.

## Open items at session end

- **L5 RETIRE vs AGREE puzzle.** `simulate_windows` says L5 → RETIRE (HOLD across 7 cutoffs, −0.5% to +4.5% margins). Divergence report says L5_ENABLED AGREE. L5 shipped 2 days ago (v0.6.248); too early to revert based on this conflict alone. Investigate — different rollups disagreeing.
- **L6 refit (Fix B)** — see [[project-l6-l2-double-counting-hypothesis]]. Wait 2–3 days of post-v0.6.259 `l6_gate_history.json` reads to see if HOLD magnitude compresses. If not, Fix B moves up.
- **Per-(field, regime, lead_band) skip table for L3/L4** — pattern confirmed on 4 fields (ws/wg/cc/cm); larger architectural commit than the calm-wind gate. Fresh-session work.
- ~~**CALM_GATE_ENABLED flip** — eligible 2026-07-02~~ → **KILLED 2026-06-30 evening** as wrong intervention. See [[feedback-calm-gate-wrong-intervention]] and [[project-ws-l3-by-regime-find]]. Removal from `decay_apply.py` queued for the next collector ship.
- **Scorecard banner** — small follow-up. Add "Stack vs raw: −X% MAE across N fields | M/N net-positive | worst regression: …" above Status. Sourced from `time_series_diagnostic.json`. ~30–40 lines of JS.

## Things in the working tree, NOT committed

- `weather_collector/data/c1_confidence_curated.json` + `_v2.json` — fresh curated tables from the digest. Ship as their own commit when ready; not bundled with the architectural work this session.
- `.cache_l5_gate_history.json` — local cache, should be in `.gitignore`.

## Lesson preserved

Asymmetric gating in evaluation logic can silently hide real signals. The walk-forward validator's "L4 requires L3 to earn its keep first" looked sensible but broke for any field where L3 wasn't going to apply anyway. Pattern codified in [[feedback-asymmetric-gates-hide-signal]].

## Post-marathon UX pass (evening 2026-06-30, frontend v0.6.263 → v0.6.266)

Driven by `Wyman_Cove_Engineering_TODO_Combined.txt`. Frontend-only debug-page work, four versions back-to-back. See git log for full per-version diffs.

- v0.6.263 — TOC/header renames (Status → Engineering updates), accuracy intro lowest-line framing, Applicability map rendered-from-code framing + Terminology key, Production Stack reframed (Core / Specialists / Confidence), Q/E/D recast of Upcoming Decisions, L3/L4 + L5 restructured to the 5-block layout, L2 row group on Applicability Map (hand-curated), R&D reorganized into Diagnostics / Candidates / Experiments, **new Archive top-level section**.
- v0.6.264 — Production line + column on accuracy charts (white, on top); removes single-"applied" framing.
- v0.6.265 — Joe's architectural redirect: dropped `.layer-active` per-column highlighting (no single applied layer under conditional gates); Production marked "Production*" with disclaimer (today's Production = approximation = MAE of deepest applied layer per field; true per-row Production needs collector to stamp `applied_layer` per pair-log row → Fitter aggregates `per_layer_mae_by_lead[field].production`). Backend ship queued.
- v0.6.266 — CALM_GATE killed (see [[feedback-calm-gate-wrong-intervention]]). PP card "MAE displayed, Brier evaluated" disclaimer banner + y-axis relabel (per-lead Brier backend ship queued). KBOS+KBVY cloud blend prose fixed — code only mutates `hourly[0]`, not propagated across leads; promotion to full per-lead L2 queued behind a Stage 0 persistence test.

## Items queued by the evening pass

In Open architectural questions on the debug page:
- **Per-row applied-layer stamping** (collector ship) → true Production line.
- **Per-lead Brier for PP** (Fitter ship) → swap PP card y-axis + band column.
- **KBOS+KBVY cloud blend → full L2** behind `analysis/h_cloud_bias_persistence.py` (gate ≥0.30 ρ at lead 6h AND ≥0.15 at lead 12h).
- **dp L4 regime cross-cut** (chart shows L4 lowest, validator below 3% threshold — likely regime-shaped).
- **Per-(field, regime, lead_band) skip table for L3/L4** — first cells: `(ws, ne_flow, *)` + `(ws, sea_breeze, 0-11h)` per the 06-30 ws-by-regime read.
- **CALM_GATE_ENABLED removal** from `decay_apply.py` — cleanup (gate is False, no-op in code).
