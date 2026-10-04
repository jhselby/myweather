---
name: selector-recency-override-watch
description: "v0.6.546 09-03 evening ship — L1 selector recency override. Watch schedule for confirming Selector Skill / Value Captured / Hit Rate recovery on the debug page, monitoring for override churn, and expected quiet-evaporation of overrides over ~2 months as pre-v0.6.540 stale data ages out of the 30d fit pool."
metadata: 
  node_type: memory
  type: project
  originSessionId: 835c70f6-1202-4836-b044-dfbb568b45f8
  modified: 2026-09-12T10:10:49.133Z
---

# L1 selector recency override — post-ship watch

Shipped 2026-09-03 evening as v0.6.546. Collector rev `00549-qug` ACTIVE at 00:18 UTC 09-04. First run on new revision at 00:27 UTC verified cold-start.

## What was shipped

`analysis/l1_selector_fit.py` gained a recency-override layer on top of the 30d pooled fit. Cell flips iff last 7d has paired n ≥ **MIN_N_RECENT=200** AND lift magnitude ≥ **MIN_LIFT_RECENT_PCT=5.0%** in the OPPOSITE direction from the 30d pick. Runtime unchanged — reads only the final `source` key. New per-cell fields are metadata: `source_30d`, `source_recent`, `override_reason`, `recent_*_prod_mae`, `recent_lift_pct`, `recent_n`.

10 overrides applied at ship, all HRRR→NBM: sr all 4 bands, h 6-11, h 12-23, dp 0-5, t 24-47, wd 0-5. ws 24-47 held as NBM by the override after 30d lift dipped below 3% base threshold (secondary stability floor behavior).

## Checkpoint 1 — Fri 09-04 morning digest

**Why:** First post-ship debug-page read. Baseline was Selector Skill median **-4.4%**, hit rate **54.1%**, value captured **-28.4% median / -16.3% mean**.

**How to apply:**
- Selector Skill median should move from -4.4% toward 0+.
- Value Captured median should climb from -28% toward 0+.
- Hit rate should lift from 54% on the 10 flipped cells.
- Losing fields h / sr / dp / wg 0-5 / wd 0-5 / t 24-47 should flip toward flat-or-winning on Total Lift.

**If no recovery visible:** check whether override fired but pair log is still stamping old picks (writeback lag). Look at `override_count` in the curated JSON, and grep pair log for `{field}_selector_source` values on rows issued post-00:18 UTC 09-04.

## Checkpoint 2 — 7-day re-check (Wed 09-10) — READ 2026-09-11

**Why:** Watch for override churn. If cells flip in and out week-to-week, MIN_LIFT_RECENT_PCT (5%) needs to go up.

**Result (read 2026-09-11 from `l1_selector_table_curated.json`, fitted_at 2026-09-11T10:29):** `override_count=9` (was 10 at ship). Diff:

| Cell | 09-04 | 09-11 | Note |
|---|---|---|---|
| sr 0-5 / 6-11 / 12-23 / 24-47 | override | override | held (4) |
| wd 0-5, dp 0-5, t 24-47 | override | override | held (3) |
| h 6-11 | override | **graduated** | 30d fit picks NBM (+10.0%, n=3724) |
| h 12-23 | override | **graduated** | 30d fit picks NBM (+9.7%, n=7380) |
| ws 24-47 | held-NBM by floor | 30d-NBM (+5.5%, n=14902) | 30d absorbed |
| **ws 12-23** | — | **NEW override** | 7d +7.6%, n=1888 |
| **wg 0-5** | — | **NEW override** | 7d +12.0%, n=942 |

**Verdict:** DO NOT tighten threshold. Strict rule counts 4 changed (2 out + 2 in) but 2 of the "outs" are **graduations** (desired quiet-evaporation arriving early, before Checkpoint 3 11-04), not churn. Real churn = 2 new adds, both with strong signal (n≥900, |lift|≥7.6%). Mechanism working as designed: overrides evaporating on schedule as 30d fit catches up, and catching new flips as NBM cascade keeps improving. Watch rule as written over-counts — should probably say "cells that flipped BACK to HRRR from override," not "cells no longer in override set."

## Checkpoint 3 — 2-month quiet-evaporation check (~11-04)

**Why:** Once pre-v0.6.540 stale data has fully aged out of the 30d fit pool (v0.6.540 landed 09-02, 30d pool rolls forward daily), the 30d pick should catch up to the current 7d evidence and the overrides should quietly evaporate.

**How to apply:**
- Expect `override_count` to drop from 10 toward 0-2 by mid-November.
- If overrides persist past 11-04, means the 7d and 30d windows have a durable disagreement — investigate whether the recency window itself should widen (14d instead of 7d) or whether a different pool bias is being papered over.

## Related

- [[09-03-session]] — the ship narrative.
- [[project_dp_v0540_warmup_watch]] — the sibling watch on dp's warmup artifact. v0.6.546 flipping dp 0-5 to NBM will accelerate that recovery on the short-lead band; long-lead bands (6-11, 12-23, 24-47) route NBM in the 30d fit already so were unaffected by the override.
- [[feedback_broader_than_gate_cleared]] — the pattern that this ship broke; cross-cutting infra shouldn't wait on individual gate maturation.
