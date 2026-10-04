---
name: feedback-fresh-routing-loss-diagnosis
description: "Before proposing a named routing gate for a fresh (<24h) routing loss on the 12h/24h table, confirm regime (nw_flow ≠ stagnant_high) and confirm sample size vs escalation clause + walker gate"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7c67af40-e0a0-4177-b868-d4878915ab22
  modified: 2026-09-15T22:01:13.464Z
---

When the 12h or 24h per-field table shows a fresh negative routing_paired_pct for a field, DON'T ship a named routing gate before verifying:

1. **The regime driver.** Split the affected bands by `state_obs.regime_synoptic` in the pair log. If bands are 100% one regime, that's your driver. Don't assume stagnant_high just because it's the newest regime label. In practice nw_flow / sw_flow / calm each dominate the 12h window at different times.
2. **The sample size vs both gates.** Escalation clause needs |lift|≥20% AND n≥500 same-day. 3-day walker gate needs sum_daily_n_in_window ≥ 60. If your candidate cell is below both, the walker will catch it in 1-2 daily reads or the regime will shift and it self-heals.
3. **The 12h pattern vs the pool.** A ws/nw_flow band that's HRRR-favored 30d (−4% NBM lift) and recent-7d neutral (−0.5%) with a fresh 12h flip to NBM +40% is a within-noise short-window swing, not a durable pattern. Named gates are for durable patterns.
4. **Blank cells vs real losses.** If the 12h table reads "—" or MAE=0, check publisher freshness first (`make deploy-publisher` state, GCS `generated_at`) before treating it as a real loss. This trap fired 09-14/15 — sr looked catastrophically negative in the 12h window because the publisher CF was 2 days stale and blanking the table.

**Why:** on 09-15 the end-of-day read flagged "fresh solar routing loss" that turned out to be the stale-publisher artifact (nothing wrong with sr, just no data flowing through the 12h window). The same read flagged "wind-speed routing loss" that was real but was 100% nw_flow, not the stagnant_high axis the diagnosis was expecting. A named stag×ws gate would have been shipped on the wrong axis. Same shape as the CALM_GATE_ENABLED failure ([[feedback_calm_gate_wrong_intervention]]) — the intended axis wasn't the failing axis.

**How to apply:** on any 12h/24h routing-loss discovery: (a) verify publisher freshness, (b) split affected bands by regime in the pair log, (c) check walker + escalation-clause thresholds against actual cell n, (d) only then propose a named gate — and prefer waiting 1-2 daily walker reads if the fresh episode is < escalation threshold. See [[project_09_15_diagnosis_sr_ws_stagnant]] for the worked case.
