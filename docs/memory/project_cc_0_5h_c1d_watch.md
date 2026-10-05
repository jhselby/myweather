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


## CLOSED 2026-10-05 — no ship, watch retired

Trigger date reached. Findings (digest 10-05 + `scripts/c1d_cc05_stability.py`, 21 trailing 14-day windows, run on the Mac):

- **The premise was structurally wrong.** `analysis/c1d_calibration.py` uses `TEST_DAYS = 14`, a *rolling* 14-day window, so `n_low` cannot grow organically; it plateaus. n_low scales with band width at ~140 rows per lead-hour (0-5h 832, 12-23h 1,709, 24-47h 3,544). The 0-5h and 6-11h bands for every field sit under `SAMPLE_FLOOR = 1000` permanently. "Wait for n to grow" never resolves.
- **The premium is not stable in magnitude.** cc/0-5h `premium_pct` over the 21 windows: +145% (09-15) -> +762% (09-29) -> +464% (10-05); max/min 5.3x. Digest run 10-05 read +429.63% (low 7.46 / high 39.49). Halves disagree wildly (e.g. 10-05: +1,285% vs +213%). The **ratio** is driven by the low-sigma MAE shrinking (12.0 -> 4.4 -> 7.0) in clear-sky stretches.
- **The direction IS stable.** The absolute gap (high - low) is positive in every window and every half (minimum half +44%): about 19 points on 09-15, 33-37 points around 10-02, 32.5 on 10-05. The user-visible-error variant (`prod_error`) is also positive throughout: +57% -> +205% -> +115%.
- **Decisive: `confidence_layer.ENABLED = False`.** The confidence block is stamped on `weather_data` for transparency but not applied, and the frontend only shows the status line when `data.confidence.applied` (`js/briefing.js`). The module comment says flip True only after the UI is wired AND the calibration audit confirms bands contain truth at the claimed rate; `c1_calibration_audit` is HOLD at 13% pass (3/23) vs the 75% bar. So a cc/0-5h C1d cell would have **zero user-visible effect today**. The KNOWN_LIVE_PIPELINES "C1d live" label means the loader is wired, not that bands are displayed.
- **Decision: do not ship, do not cap, close the watch.** Revisit only if the confidence layer gets a real enable plan. If it does: use the absolute gap (or a capped widen) instead of premium_pct, and re-measure on a window that excludes the 09-30..10-02 event.
