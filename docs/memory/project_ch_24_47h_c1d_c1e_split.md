---
name: ch-24-47h-c1d-c1e-split
description: "NEXT SESSION cold-start brief. ch/24-47h C1d ships pooled NARROW -16.4% but observed σH/σL splits badly across regimes: baseline 0.93× (mild NARROW) vs post-front (C1e=True) 3.20× (wants WIDEN hard). Pooled premium is averaging two opposite signals. Propose split into C1d × C1e joint cell. Architectural session — schema/wiring verification required before any ship."
metadata: 
  node_type: memory
  type: project
  originSessionId: 73f1099e-9f76-4dd3-ad09-043a34fc9779
  modified: 2026-09-14T16:37:53.955Z
---

# ch/24-47h C1a-conditional recalibration — cold-start brief

Queued 09-14 as item 3 of [[09-14-queued-investigations]]. Items 1 and 2 are resolved (v0.6.618 ship and no-op watch respectively). This is the last one open from that day.

## The finding

Source: [[project_c1d_kill_scope_artifact_09_14]] — surfaced during the v0.6.616 orthogonality investigation.

`ch/24-47h` C1d cell currently ships:
- **Pooled premium: NARROW −16.4%** (in `weather_collector/data/c1d_curated.json`)
- Rationale: pooled σH/σL under baseline conditions is ~0.93× (high-σ has slightly LESS error → mild NARROW)

But when split by C1e (post-frontal window, hsf<24h):
- **Baseline** (no-front, no-trans): σH/σL = **0.93×** → mild NARROW (matches pooled)
- **Post-front** (C1e=True): σH/σL = **3.20×** → wants **WIDEN hard**

The pooled −16.4% is averaging a NARROW baseline with a WIDEN post-front, so displayed-band accuracy is *actively wrong* in post-frontal 24-47h windows — tightening the confidence band right when uncertainty is 3× larger.

## What needs verifying (session-1 work)

Before proposing any ship:

1. **Does `c1_confidence_curated_v2.json` already support C1d × C1e joint cells?** Memory says it supports axis combinations via `by_axes` — verify that's live and how joint cells fire in `weather_collector/processors/confidence_layer.py`. Look for the loader (probably near `_load_marginal_table` at line 254) and the fire logic (around `c1d_cell` handling at line 872).
2. **What's n for the post-front subset at ch/24-47h?** If n_high in post-front is <100, this is thin and needs to sit longer. The pooled cell has n_low=2596/n_high=2520 — post-front is a subset, could be tiny.
3. **Halves-stability on the post-front cell.** Same pipeline discipline that won today (v0.6.618) and blocked yesterday's cc/0-5h ship. Don't ship without it.

## Ship shape (if all checks clear)

Shadow-first: shadow-write the C1a-conditional variant, measure counterfactual displayed-band accuracy over 7 days, then flip. Don't apply the split to production directly on day 1 — same rule that shipped v0.6.618 cleanly.

## How to open the session

1. Read `weather_collector/data/c1d_curated.json` — confirm current ch/24-47h NARROW −16.4% (n_low=2596, n_high=2520).
2. Read `weather_collector/data/c1_confidence_curated_v2.json` — check if `by_axes` C1d × C1e cells already exist for anything, understand the schema.
3. Read `weather_collector/processors/confidence_layer.py:254-905` — trace how joint-axis cells fire (if at all).
4. Locate the orthogonality output that surfaced the 3.20× post-front finding — likely `analysis/output/h_cloud_disagreement_orthogonality.txt` (already contains the C1d × C1e cross-cut) or the c1d_kill_scope investigation file from 09-14.
5. Compute (or find) n for post-front subset at ch/24-47h. If thin, this is a no-op-with-watch outcome like item 2.

## Success criterion

Decide whether to split ch/24-47h's C1d cell into two conditional cells (baseline + post-front), and either ship the split (shadow-first) or document why the pooled premium remains best (with a watch trigger if new evidence would change that).

## Related

- [[09-14-queued-investigations]] — parent brief (items 1, 2 resolved; this is item 3).
- [[project_09_14_session]] — session context where this surfaced.
- [[project_c1d_kill_scope_artifact_09_14]] — evidence base.
- [[project_cc_0_5h_c1d_watch]] — item 2 resolution (no-op with watch) as a template for how thin-sample findings should land.
- [[feedback_hypothesis_promotion_pipeline]] — pipeline discipline (halves + rolling stability) that both today's ship and today's no-op honored.
