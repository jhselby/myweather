---
name: project-dynamic-omega-ims-conditioning
description: "v0.7.7+ backlog. Tested 09-26 as long-shot vs v0.7.6 static ω. Dynamic ω binned by ims-quartile: field-mean +1.5pp/+1.2pp on dp both halves, ~null on h. Specific cell dp/ne_flow/24-47 gains +11-18pp. Real signal but not enough to overturn static ship. Real follow-up: test ims-conditioning on DIVERGE cells (0-5h short leads) to see if it rescues them."
metadata: 
  node_type: memory
  type: project
  modified: 2026-09-26T17:22:25.183Z
  originSessionId: b263e9cd-d969-4acf-add7-b0c4f9f5625c
---

# Dynamic ω via ims-quartile conditioning — v0.7.7+ backlog

## Result summary (2026-09-26, tested against v0.7.6 static ω)

Tested `blend_omega = f(ims_quartile)` where each STABLE cell's rows are binned into 4 ims quartiles at train time and ω fit per bin.

**Halves-A/B deltas (dynamic − static, weighted):**
- h: −0.94pp on A, +0.69pp on B → net wash
- dp: **+1.53pp on A, +1.18pp on B** → both halves positive, real but modest

**Standout cell:** `dp/ne_flow/24-47`
- Static ω=0.17: lift +13.4% / +15.1%
- Dynamic ω=[0.00, 0.00, 0.00, 0.20]: lift +24.7% / +33.1%
- Pattern: pure NBM when models agree, 20% HRRR when they disagree strongly.

**Mean ω per ims-quartile Q1→Q4:**
- h: 0.31 → 0.42 → 0.39 → 0.46 (mild upward, "more HRRR when models fight")
- dp: 0.27 → 0.20 → 0.22 → 0.27 (flat at field level; cells drive the gain)

## Why this stays backlog (not urgent)

- +1-2pp lift on dp only doesn't overturn the static ship. v0.7.6 shadow is validating universal ω per field; measuring dynamic on top requires the static ship to first go live and prove its own baseline.
- More promising follow-up: **test ims-conditioning on the DIVERGE cells** (0-5h short leads and ne_flow across fields) that v0.7.6 doesn't cover. Those cells lost to cascade under static ω. If dynamic ω per quartile rescues them, coverage expands beyond the current 20 cells.

## When to revisit

- After v0.7.7 apply-flip lands and 30d of live data confirms static ω is producing the promised +18-30% on covered cells.
- OR: if a user notices dp still has bad rows despite v0.7.7 apply — the standout cell suggests specific structural gains sit outside static's reach.

## Files

- Analysis script: `/private/tmp/claude-503/.../scratchpad/dynamic_omega_by_ims.py`

## Related

- [[project_l1_static_blend_v076]] — v0.7.6 shadow ship this refinement builds on.
- [[project_09_26_session]] — session narrative.
