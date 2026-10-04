---
name: project_cc_combine_walker
description: "Ccd's FORMULA constant (currently hardcoded `max`) is the last static combine in the cloud stack. Replace with a per-(regime × lead-band) dynamic gate + 7-day stability walker — same design pattern as Lc/chp/Lsr gates. Motivated by h_cc_derivation re-run 2026-08-17 showing random-overlap now beats max by +8.73% pooled, wins 9/9 regimes."
metadata: 
  node_type: memory
  type: project
  originSessionId: 88021b04-0fee-492f-9d9b-c7a25f4a38db
  modified: 2026-08-17T22:03:59.838Z
---

# Opened 2026-08-17

**Problem.** `weather_collector/processors/cc_from_derivation.py` has two hardcoded constants that drift:
- `FORMULA = "max"` — chosen 07-30 from a one-shot h_cc_derivation run. No mechanism to re-check.
- `SKIP_REGIMES = frozenset({"se_flow", "unknown"})` — same shape as chp `_CELL_SKIP`: hand-typed, never removed.

**The trigger.** 2026-08-17 re-ran `h_cc_derivation` on current pair log (n=34,129 quads, obs ≥ 2026-07-01):
- random-overlap MAE 21.398 vs max 23.296 vs prod 23.446 — **random beats max by +8.13%, beats prod by +8.73% pooled**
- **9/9 regimes** — every regime prefers random, including the two currently in SKIP_REGIMES (se_flow +10.03% for random, +3.57% for sea_breeze)
- Halves: half A random +0.86%, max −13.03%; half B random +16.55%, max +14.21% — random dominates and is stable
- 14-day daily rows: random beats max on 11/14 days, by 20-45% on the noisiest days
- Verdict: PROMOTE random.

`max` is losing ground because HRRR post-Lc corrections push individual layers higher; `max` amplifies that, while `random` de-correlates. Physical justification from cc_from_derivation.py header (max reflects METAR "highest broken/overcast layer") turned out empirically weaker than assumed.

## Why (design principle)

Same anti-scar-tissue motivation as [[project_chp_cell_skip_to_dynamic_gate]] and [[project_lc_regime_conditional]]: hand-typed constants selected on a snapshot age silently as HRRR / Lc behavior drifts. The correction: make the choice per-(regime × lead-band × formula) and reselect daily on a rolling window, with a 7-day stability floor so noise days don't cause flips.

## How to apply

Mirror the Lc/chp gate architecture:

1. **Analysis script** `analysis/h_cc_combine_walker.py` — reads the pair log daily, aggregates MAE per (regime × lead-band) for {prod, max, random} on today's window, appends per-cell "which formula won today?" to `.cache_cc_combine_history.json`. Per-cell 7-day gate rule: `formula = "random"` only if random wins on the majority of the last 7 seen days (mirror chp's conservative "all-lose" rule). Emits `weather_collector/data/cc_combine_gate.json`.

2. **Runtime consumer** in `cc_from_derivation.py`: add `CC_COMBINE_GATE_ENABLED = False` toggle + `_load_combine_gate()` + per-lead formula selection inside `_derive()`. Ship OFF-first (v0.6.4XX). When ENABLED=True, per-cell formula in the runtime table overrides the module-level `FORMULA` default.

3. **Flip pattern**: 7-day walker seed → per-cell stability → flip `CC_COMBINE_GATE_ENABLED = True` in a follow-up ship (same v0.6.410 → v0.6.413 shape).

4. **Migration**: `SKIP_REGIMES` frozenset stays as belt-and-suspenders during the seeding window. Once the gate table shows a stable non-`max` formula (or "hold-prod") for a regime, retire that regime from SKIP_REGIMES.

**Do NOT** hand-edit `FORMULA` or `SKIP_REGIMES` while this workstream is open. Only exception: an outright regression where cc MAE% > +50% for multiple regimes that can't wait for the 7-day gate.

## 2026-08-17 — Stage 0/1 walker seeded

- **New `analysis/h_cc_combine_walker.py`** — daily per-cell walker.
- **Day 1/7 seeded 2026-08-17.**
- **Stage 3 wire NOT shipped yet** — analysis-only for now. Will follow same pattern as chp v0.6.421 (wire OFF in a separate collector redeploy).

## Sibling context

- [[project_cc_derived_field]] — original Ccd ship (07-30)
- [[project_cc_composition_pure]] — formula error using observed components (isolates formula from cascade)
- [[project_cc_blend_tuner]] — parametric blend candidate (deferred; walker is smaller surface)
- [[project_chp_cell_skip_to_dynamic_gate]] — sibling architecture
- [[project_lc_regime_conditional]] — successful precedent
- [[feedback_dont_over_gate]] — general principle
