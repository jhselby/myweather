---
name: feedback-tau-suspect-can-be-selector-artifact
description: "The layer-shape sentry's τ-suspect alert (helps short lead, hurts long lead) can fire from selector anti-selection, not a decay-τ problem, even when its own L2-applied gate passes. Check the L2-counterfactual-on-every-row number before recommending 'shorten τ or add a SKIP.'"
metadata:
  node_type: memory
  type: feedback
  modified: 2026-10-06T16:00:00.000Z
---

# Rule

Before accepting a layer-shape sentry τ-suspect alert's own prescription ("shorten τ or add a
lead-band SKIP"), check whether the correction layer itself (`error_l2`, computed over every row
in that band, not just the rows where it was actually served) is really the thing causing the
hurt. Compare three numbers on the *same row population*: raw (`error_l1`), the correction layer
counterfactual (`error_l2`), and real production (`error_{applied_layer}` via `_prod.prod_error`).

If the L2 counterfactual is neutral-or-better than raw at the "hurt" band, the hurt isn't a decay
problem — it's the **selector** choosing among sources (`l2_nbm`/`l4`/`l2`/`l1`) in a way that
underperforms simply committing to L2. Shortening τ or adding a SKIP does nothing for that; the fix
(if any) lives in the selector's criteria for that (field, regime, band), not in the decay fit.

## Why

2026-10-06: both `h/production` (12-23h) and `t/production` (6-11h) fired as τ-suspect. The sentry's
own `L2_APPLIED_MIN_PCT` gate (`build_executive_summary.py:1066-1081`) only checks that L2 differs
from raw by ≥1% at the hurt band — it does NOT check that L2 is the one making things worse. On
both fields that day, L2-for-every-row *beat* raw (h: 4.50 vs 4.97; t: 1.63 vs 1.67), while served
production was 15-16% worse than raw because the selector split the band across sources that each
individually lost to committing to L2. The gate passed (L2 differed from raw by more than 1%, just
in the helping direction) and the alert fired anyway, labeled as a decay-constant problem it wasn't.

This is a **different mechanism** from the sentry code's own documented 2026-09-08 precedent
(where L2 had fully decayed to match raw, and a deeper layer/selector pick was the real driver —
see [[project_09_08_session]]). That case the code comment already guards against via the
`_l2_applied` check. This case slips past that same guard because L2 *does* differ from raw — it
differs in the direction that would have helped, not hurt.

## How to apply

- Any τ-suspect (★) alert: before recommending a τ change, pull the pair log for that (field, band)
  over the same window, filter to that band, and compute mean(`error_l1`), mean(`error_l2`) across
  every row, and mean(`prod_error`) (via `analysis._prod.prod_error`). If L2-on-every-row is
  neutral-or-better than raw, the τ framing is wrong — go look at `selector_mechanism` /
  `applied_layer` splits for that cell instead.
- If L2 itself IS worse than raw at that band, the original τ-suspect framing may be correct —
  this rule only flags the specific failure mode where L2 is fine and the selector is the problem.
- Don't ship a τ/SKIP fix off the alert text alone. The sentry is a tripwire, not a diagnosis.

Related: [[project_layer_shape_sentry]] (the tool, its known gaps), [[project_09_08_session]] (the
documented precedent this is a sibling of), [[project_10_06_session]] (where this was found),
[[feedback_digest_triage_discipline]] (state hypothesis as hypothesis — this finding is one day's
window and unverified for stability).
