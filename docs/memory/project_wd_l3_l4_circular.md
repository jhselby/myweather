---
name: wd-l3-l4-circular
description: "Plan to wire wd into L3 and L4 by building circular-math primitives (residual, mean, apply, MAE) shared across Fitter + Apply. Currently blocked because decay_fit/decay_apply use scalar arithmetic. Order: wdp ships 07-27 first, then circular primitives, then wd → L3_FIELDS + L4_FIELDS one-liners, then normal Stage 0/1/2/7-day gate per layer."
metadata: 
  node_type: memory
  type: project
  originSessionId: fa235c28-5333-4ea7-b272-5b2905577a5f
  modified: 2026-07-20T23:21:03.322Z
---

# wd L3 + L4 wiring — circular primitives plan

Decided 07-20 evening after Joe pushed back on my initial "L4 probably not worth it" answer. That was pre-filtering; the right pattern per [[feedback-best-way-first]] and [[feedback-dont-over-gate]] is: build once, wire wd through the same L3/L4 pipeline as every other field, let Stage 0/1/2 gates decide what ships.

## The one real distinction

wd is circular; every other field is linear. `decay_fit.py` and `decay_apply.py` compute residuals as `obs - fc` scalar arithmetic and store corrections as scalar Δ. For wd that's broken across the 0/360 seam. Everything else about wd (whitelist membership, skip-table structure, Stage 0/1/2 gate, 7-day narrow-promote) is the same shape as every other field.

## Primitives to build (one-time, shared across L3 + L4 + wdp + future circular fields)

1. **Circular residual.** `circ_diff(obs, fc) → signed Δθ in [-180, 180)`. Exists in `analysis/h_ws_wd_error.py:22-24`; extract to a shared util (probably `weather_collector/utils/circular.py` or extend an existing utils module).
2. **Circular mean of residuals.** Unit-vector: `mean_θ = atan2(mean(sin(θᵢ)), mean(cos(θᵢ)))`. Same pattern `wind_blend.py` already uses for L2 — refactor to import from the new util.
3. **Circular apply.** `(fc + Δθ) mod 360` in `decay_apply.py`, gated on which fields are circular via a `CIRCULAR_FIELDS = {"wd"}` set.
4. **Circular MAE/RMSE in Fitter.** `per_layer_mae_by_lead["wd"]` needs `mean(|circ_diff|)`, not `mean(|obs - fc|)`. Joiner already does this correctly for wd's pair rows post-v0.6.367 — extend the same treatment to L3/L4 fit-time reporting inside `decay_fit.py:1148-1226` area.

## Wiring after primitives

After the primitives exist and are toggled by `CIRCULAR_FIELDS`:
- **L3 wd:** `L3_FIELDS.add("wd")`. Skip-table generation should work as-is because it's cell-membership logic, not arithmetic.
- **L4 wd:** `L4_FIELDS.add("wd")`. Diurnal per-hour-of-day residual now well-defined via circular mean.

Both become one-line additions to the whitelist sets. Then normal Stage 0 → Stage 1 → Stage 2 → 7-day gate per layer, same as every other field.

## Effort

- **Circular primitives + Fitter/Apply plumbing:** ~4–6 hours (shared across L3, L4, and future).
- **L3 wd whitelist + verify:** trivial after primitives.
- **L4 wd whitelist + verify:** trivial after primitives.
- **Stage 0 → Stage 1 → Stage 2 → 7-day gate for each layer:** ~2 weeks per layer at normal cadence, same as every other candidate.

## Order

1. **wdp (wd_persistence_gate)** — ships 07-27 per [[wd-persistence-gate]] existing plan. Do this first; don't destabilize the persistence gate work by refactoring the Fitter underneath it.
2. **Circular primitives + Fitter/Apply plumbing** — start after wdp is live and 14-day watch is clean, roughly 08-10+.
3. **L3 wd** — one-liner + Stage 0/1/2 pipeline. Earliest ship ~4 weeks after primitives land.
4. **L4 wd** — one-liner + Stage 0/1/2 pipeline. Can run concurrently with L3 wd from Stage 0 onward if desired.

## What I was wrong about initially

Speculated that L4 wd diurnal would "duplicate sea-breeze regime" and be "not worth building." That's pre-filtering exactly the kind that [[feedback-best-way-first]] and [[feedback-dont-over-gate]] flag. The pipeline exists to measure — sea-breeze regime tagging and per-hour-of-day circular mean bias correction measure different things, and only Stage 0 can tell whether the residual after regime correction is small enough to skip L4. Withdrawn.

## Related

- [[wd-l2-blend]] — first wd correction shipped; introduced the circular-math pattern in `wind_blend.py`
- [[wd-persistence-gate]] — second wd correction (wdp), blocking this work until it lands
- [[feedback-best-way-first]] — don't pre-filter; present the option, let Joe decide
- [[feedback-dont-over-gate]] — live-layer change gate governs flips, not exploration
