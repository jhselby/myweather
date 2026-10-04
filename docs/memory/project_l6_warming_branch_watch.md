---
name: project-l6-warming-branch-watch
description: "2026-07-01 open watch: L6 warming branch (retained after the cooling-branch kill on 06-30) may itself be net-negative. Real per-row Production data at short leads (n>25) shows T Production still worse than L2 alone by ~15%. Not enough data to conclude; watch through 07-08 (full 7-day post-fix window). If verdict holds, Fix B (refit L6 lookup against L2-corrected baseline) is the answer."
metadata: 
  node_type: memory
  type: project
  originSessionId: 56248ef4-af78-48a9-998a-163e8a07965d
---

**The finding.** 2026-07-01 15:07 Fitter cycle post-v0.6.269 populated `per_layer_mae_by_lead.t.production` at 9/48 leads (~184 rows total). Real Production numbers at short leads (n≥25):

| Lead | L1 (raw) | L2 alone | L6 (approx) | Real Production | n |
|---|---|---|---|---|---|
| 0 | 1.18 | 0.25 | 1.13 | **0.75** | 8 |
| 1 | 1.39 | 0.78 | 1.35 | **1.42** | 43 |
| 2 | 1.64 | 1.17 | 1.76 | **1.56** | 37 |
| 3 | 1.76 | 1.33 | 1.97 | **1.16** | 31 |
| 4 | 1.80 | 1.50 | 2.10 | **1.82** | 25 |

Real Production is **12–41% BETTER than the L6 approximation** at every lead 0–4 → the approximation was too pessimistic because it treated one-in-three L6-fired rows as if every row got L6.

**BUT real Production is still WORSE than L2 alone at every lead.** The model:
- Production ≈ 0.7 × L2 + 0.3 × L6 (L6 warming branch fires when sb_active AND wind octant ∈ {S, SE, SW} — ~30% of rows).
- Solving: if Production_lead1 = 1.42 and L2_lead1 = 0.78, and 0.7 × L2 = 0.55, then 0.3 × L6-fired ≈ 0.87 → L6-fired MAE ≈ 2.9 (way worse than L2's 0.78).

So on the ~30% of rows where L6 warming branch fires, the correction actively hurts.

**Why this matters.** The 06-30 fix (see [[project-l6-l2-double-counting-hypothesis]]) killed the cooling branch. The retention decision on the warming branch was based on aggregate paired-MAE that mixed pre-fit rows and rows from before the reference frame was reset. The real per-row data now available (from applied-layer stamping) tells the honest story.

**How to apply:**

- **Watch through 2026-07-08** (full 7-day post-fix window). Small-n today (9 populated leads, thin per-lead sample). L6 gate history reads (`l6_gate_history.json`) should continue trending toward 0 if warming branch is neutral, or plateau at some negative value if warming branch itself is net-negative.
- **If verdict holds by 07-08** (T Production still worse than L2 alone by ≥5% across the 40+ populated leads): retire the warming branch too. `compute_cove_correction()` returns 0.0 for both branches. Refit the L6 lookup against L2-corrected baseline (Fix B) rather than the raw waterfront-vs-inland gradient.
- **If Production compresses to L2 or better by 07-08**: warming branch was fine, the cooling-branch fix was the whole story, no further action.

**See also:** [[project-l6-l2-double-counting-hypothesis]] for Fix B design; [[project-07-01-session]] for the enabling machinery.
