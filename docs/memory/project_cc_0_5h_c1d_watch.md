---
name: cc-0-5h-c1d-watch
description: "cc/0-5h C1d cell — exceptional orthogonality (only cell clean on BOTH C1a AND C1e) with premium +137.92% WIDEN, but SKIP'd at sample floor (n_low=736/n_high=582 vs 1000). No-op with watch: expect standard SAMPLE_FLOOR gate to auto-promote as n grows organically (~2-3 weeks). Revisit only if n_low still <1000 by ~2026-10-05 — that would indicate structural undersampling and justify a lower-floor tier."
metadata: 
  node_type: memory
  type: project
  originSessionId: 73f1099e-9f76-4dd3-ad09-043a34fc9779
  modified: 2026-09-14T16:26:52.948Z
---

# cc/0-5h C1d — watch, don't intervene

Investigated 09-14 as item 2 of [[09-14-queued-investigations]]. Resolution: **no-op with watch**.

## The signal

cc/0-5h C1d cell surfaced in the v0.6.616 orthogonality re-run:
- **Premium:** +137.92% WIDEN (low-σ MAE 13.56, high-σ MAE 32.27 — a 2.4× ratio at high KBOS-KBVY cloud disagreement)
- **Sample:** n_low=736, n_high=582 — 66% of `SAMPLE_FLOOR=1000` in `analysis/c1d_curate.py`
- **Orthogonality:** uniquely clean — the only cell across all 20 C1d field×band entries that is ORTHOGONAL on BOTH axes (2.57×/2.82× vs C1a, 2.57×/3.38× vs C1e). Only 3 of 20 are ORTHOGONAL on either axis; cc/0-5h is the only one on both.
- **Halves stability:** not computed — no c1d halves tool exists
- **Rolling stability:** not tracked — no history file for `c1d_confidence_premium.json`. Day-1 signal
- **Loader:** `_load_marginal_table` in `weather_collector/processors/confidence_layer.py:254` wires SHIP+MARGINAL with no premium cap. 137.92% would apply unmodified

## Why no-op

Shipping a day-1 signal with n<floor and no halves would break the pipeline discipline that paid off this morning (v0.6.618 h L2 soft_ramp retune needed 7/7 rolling STABLE + halves-clean before ship). The SAMPLE_FLOOR exists exactly to block this shape.

Signal is mechanistically defensible and the orthogonality is exceptional, but that's a reason to trust the standard gate will eventually promote it — not to override the gate on day 1.

## Watch

**Trigger date: 2026-10-05** (~3 weeks). By then, if the c1d stage1 walker has advanced past n_low=1000 for cc/0-5h, the standard curator will auto-promote — no manual action needed.

**Escalate only if n_low is STILL <1000 by that date.** That indicates structural undersampling of the low-σ (KBOS/KBVY-agreeing) bin at 0-5h — plausible mechanism: high cloud disagreement is common enough that "agreement" bins fill more slowly. If that's the situation, revisit:
1. Add a NARROW_SHIP tier to `c1d_curate.py` (lower floor n≥500, higher magnitude floor ≥50%, optional premium cap).
2. Or, per-cell hardcode SHIP for cc/0-5h with capped premium (e.g., 50%).

## Related

- [[09-14-queued-investigations]] — parent brief.
- [[project_c1d_kill_scope_artifact_09_14]] — where the cc/0-5h finding surfaced (from the C1d KILL orthogonality re-run at MIN_N=50).
- [[project_09_14_session]] — session context.
- [[feedback_hypothesis_promotion_pipeline]] — the discipline being honored by no-op.
