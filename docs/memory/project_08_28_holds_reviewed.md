---
name: 08-28-holds-reviewed
description: "Four ship-adjacent proposals reviewed and HELD on 2026-08-28 — so tomorrow's session doesn't rediscover them as noise."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8c047e09-3a34-4078-b6a2-c36aecb5ff73
  modified: 2026-08-28T11:41:33.193Z
---

**08-28 review holds** — four proposals surfaced by the digest that looked ship-ish but did not clear their ship gates. Reviewed, held, documented here so we don't spin on them again.

1. **`l6_nbm: DROP t`** — walkforward proposes dropping t from l6_nbm. Sentry shows THIN n=0 for `t.l6_nbm`. Layer doesn't actually fire. Related to Lt retired 07-13 mechanism (see [[project_lt_fix_b_answered]]). No action.

2. **`wdp_nbm: DROP wd`** — walkforward proposes dropping wd from wdp_nbm. Sentry shows `wd.wdp_nbm` THIN n_sustained=95 / n_fresh=49. Layer barely fires. Aggregate-only proposal with no cell-level breakdown; not actionable on a THIN sample. No action.

3. **`h_lc_recent_bias_gate`** — Stage 1 halves-strict PROMOTE for ch, but rolling 7-day gate: `gate_clear=False`, ch per-field streak 1/7, promoted-field set stability CHURN (ch newly promoted today, wasn't previously). Digest verdict says PROMOTE but the ship gate needs 7+ distinct days with no HOLD days and a stable set. Not ready.

4. **`l6_fix_b_refit`** — day-only +1.19% (below the ship threshold) and 7-day gate not cleared (6 HOLD days out of 7, ship_bins CHURN). Day-only signal + churny bins. Not ready.

**How to apply:** If any of these re-appear on tomorrow's digest with the same "PROMOTE/DROP" label, don't dig — they're already reviewed. Reopen only if the ship gate flips (set-stability STABLE for #3, ≥5 promote days for #4) or if the underlying mechanism changes (layer starts firing meaningfully for #1/#2).

**Related:** [[cc-l4-nbm-watch-08-28]], [[nbm-skip-proposals-review]].
