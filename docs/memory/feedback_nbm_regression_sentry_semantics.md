---
name: nbm-regression-sentry-semantics
description: NBM regression sentry compares a layer to ITSELF (sustained vs fresh MAE); it does not gate ship-worthiness. Always cross-check walkforward + product-level lift before treating a HOT as a real regression.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1df0189e-d097-47bd-a4f9-1a1782a594e2
  modified: 2026-08-29T10:22:36.714Z
---

**Rule:** When the digest's `NBM regression sentry` fires HOT on a layer (e.g. `ch.chp_nbm HOT +118%`), do NOT treat it as a ship-worthiness signal. It compares the layer's own sustained-window MAE vs its fresh-window MAE — a self-vs-self mixture-sensitive check.

**Why:** 08-29 wasted a check on `ch.chp_nbm HOT +118.2%` (fresh 16.5 vs sust 7.5). Reality: 14d walkforward chp_nbm vs l4_nbm was **EARN +59.3%** and product-level ch Total Lift was **+65.77% 7d / +65.07% 24h**. chp_nbm at 16.5 was still crushing l4_nbm at 26.0. Same false alarm as 08-27 ("self-clearing / shadow-write"). n_fresh was 606 — small enough for regime mixture to move the number 2×.

**How to apply:** On any HOT sentry, before spending a session on it:
1. Check the same layer's walkforward verdict vs its baseline — if EARN with material lift, the sentry is noise.
2. Check the field's 7d + 24h product-level Total Lift — if both positive and consistent, no regression.
3. Only investigate when sentry HOT AND walkforward flips to SKIP/LOSE AND product-level lift is degrading. All three, not any one.

Related: [[feedback_pooled_n_time_thin]] (short-window noise), [[feedback_mixture_check_window_semantics]].
