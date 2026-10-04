---
name: two-gates-per-layer
description: "For layers with a fitter script (Lc, potentially others), the DIGEST divergence-report streak counter and the fitter's own internal stability gate are TWO different gates. Both must be green before flipping ENABLED. Divergence at N/7 alone is not sufficient."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5f6682ba-1f77-4f0a-b937-3cc5b3babc09
---

## Rule

Before flipping `LC_ENABLED` (or any similar layer flag) based on the
DIGEST exec summary's streak counter, cross-check the fitter script's
own internal gate output. They can disagree.

## Why

The divergence-report streak (e.g. `LC_ENABLED  ⏳ 6/7 (1 to go)`) just
counts daily "verdict wants ship" reads. It does NOT check whether the
SHIP set itself is stable.

`lc_fit.py` has its OWN 7-day rolling gate that additionally requires:
- ≥7 distinct days
- no HOLD days in the window
- **no SHIP-set changes within the window**

If any cell flips into or out of the SHIP set within the 7 days, that
gate says `gate_clear: False` even though the divergence streak keeps
counting up.

**Concrete example (2026-07-15 digest):**
- Divergence report: `LC_ENABLED  ⏳ 6/7 (1 to go)` — looked ready.
- `lc_fit` internal gate: `gate_clear: False · SHIP-cell stability:
  CHANGED · cm 20-50: not-SHIP → SHIP`.

If Joe had flipped `LC_ENABLED=True` at 7/7 the next morning based on
the divergence counter alone, he'd have shipped an unstable SHIP set.

## How to apply

When any layer's divergence streak is at N-1/7 or N/7, before
recommending the flip:

1. Grep the DIGEST for the corresponding fitter section (e.g.
   `[OK     ] lc_fit`).
2. Look for the fitter's own "gate" or "gate_clear" line.
3. If the fitter's own gate says False for stability/set-change
   reasons, HOLD even if the divergence counter clears.

## Related

- [[project_lt_fix_b_answered]] — different problem (mechanism vs script
  verdict), same pattern: don't act on one signal without checking the
  other.
- [[feedback_regime_gate_first]] — the anti-overfit gate framework this
  layered-gate check is part of.
