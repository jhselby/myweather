---
name: dp-derived-field
description: "dp is a derived field. observed_dp = Magnus(observed_t, observed_h) via obs_log.py:80-86 (overwrites even direct Tempest sensor readings). production_dp = Magnus(corrected_t, corrected_h). So dp_error is a deterministic function of (t_error, h_error) with zero independent signal. Excluded from scoreboard aggregate v0.6.390i (2026-07-31). Cleaner double-count case than cc — dp has no tunable composition surface (Magnus is a physical constant, not a choice)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 434af779-9797-4cea-bd88-1e0939ffeef0
  modified: 2026-07-31T16:13:32.819Z
---

# dp is a derived field — excluded from scoreboard mean

**Decision:** 2026-07-31 v0.6.390i — added dp to `DERIVED_FIELDS` set in `corrections_debug.html` alongside cc. Same reasoning shape, cleaner math.

## The math

- **observed_dp** = `magnus_dew_point_f(observed_t, observed_h)` — from `obs_log.py:80-86`. Overwrites any direct dp sensor reading (Tempest at `fetchers/tempest.py:150` provides one, but obs_log discards it in favor of the Magnus derivation).
- **production_dp** = `magnus_dew_point_f(corrected_t, corrected_h)` — from `corrected_hourly.py:237`.
- **dp_error** = production_dp − observed_dp = Magnus(corrected_t, corrected_h) − Magnus(observed_t, observed_h).

That's a deterministic (nonlinear) function of (t_error, h_error). Fully computable from scoring t and h separately. Zero independent decision surface.

## Why this is cleaner than cc

cc has TWO error sources:
1. Cascade — cl/cm/ch corrections through the formula
2. Composition — formula CHOICE (max/random/max_random) vs METAR total sky cover

dp has ONE source: cascade. Magnus is a physical constant, not a tunable formula choice. No composition surface exists.

So keeping dp out of the mean is even less contentious than cc. There's no "tuner might surface signal" caveat.

## How to apply

- **Do not re-add dp to the scoreboard aggregate.** Its error is Magnus of t+h errors — counting dp in the mean triple-counts humidity through the triangle (t, h separately + h again as component of dp).
- **On any "score dp" analysis:** the answer is always in scoring t + h. Any dp-specific script is measuring redundant information UNLESS a specialist is active.
- **Reversibility:** single-line edit to `DERIVED_FIELDS` in `corrections_debug.html`. Removing dp reintroduces double-counting.

## When to revisit — specialist flips

dp has two specialists in shadow-wire that WOULD add independent structure when enabled:

- **dprp** (`dp_residual_persistence.py`, v0.6.380, ENABLED=False, flip gate 08-01) — operates on `corrected_dew_point_post_l2`, adds regime × lead_band bypass
- **dpbp** (`dp_bias_persistence.py`, v0.6.387, ENABLED=False, flip gate 08-04) — antecedent-error correction, fires when `prev_24h_dp_bias(regime) < -1.5°F`

If either flips ENABLED=True, dp gets a correction that is NOT a function of t and h. That's real independent decision surface worth scoring.

**Plan when specialists flip:**
- Do NOT put dp back in the scoreboard mean (would still double-count cascade)
- Add a separate "dp specialists" line measuring only `specialist_output - Magnus(corrected_t, corrected_h)` — the part that isn't cascade
- Include that in the mean

Same pattern as the plan for cc composition scoring in `[[project_cc_composition_pure]]`.

## Related

- [[project_cc_derived_field]] — cc equivalent (with two error sources instead of one)
- [[project_cc_composition_pure]] — the scoring pattern to reuse for dp specialists
- [[project_cc_is_blend_of_clchcm]] — the architectural observation about the Magnus triangle
- [[project_dp_residual_persistence]] — dprp specialist watch
- [[project_antecedent_pattern_generalization]] — dpbp specialist watch
- [[project_07_31_session]] — session where Joe pushed this framing to a decision
