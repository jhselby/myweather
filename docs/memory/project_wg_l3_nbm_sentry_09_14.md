---
name: wg-l3-nbm-sentry-09-14
description: "09-14 sentry HOT on wg.l3_nbm investigated — 3-day dip, not skip-worthy. Two-window gate correctly excludes. Watch frontal/24-47h — trending negative all windows, 14d -4.5% still under -3% ADD threshold, could surface as CONFIRMED in 3-4 days."
metadata: 
  node_type: memory
  type: project
  originSessionId: c656ec98-2726-4d09-8e93-674722e5843d
  modified: 2026-09-14T11:14:41.027Z
---

# wg.l3_nbm sentry HOT — 09-14 investigation

Sentry flagged fresh 3d (09-11→09-14) layer help −2.36% vs sustained 7d (09-04→09-11) +1.06%. Δ=−3.43pp. Investigated per-regime × band; **no ship warranted.**

## Per-cell windowed lifts (wg.l3_nbm vs wg.l2_nbm baseline)

| cell | fresh 3d | sust 7d | 14d | 30d | 50d | halves 50d |
|---|---|---|---|---|---|---|
| nw_flow 24-47h | −14.02% (n=307) | +6.64% (n=1225) | +2.95% (n=1638) | +2.95% (n=3025) | +1.75% (n=4387) | +0.70 / +2.98 ✓ |
| frontal 24-47h | −11.18% (n=69) | −5.93% (n=78) | −4.54% (n=186) | −1.61% (n=390) | −1.26% (n=483) | +0.38 / −2.74 ✗ |
| pre_frontal 24-47h | −3.41% (n=220) | −0.14% (n=552) | +2.40% (n=1041) | +3.05% (n=2410) | +1.63% (n=4088) | 0.00 / +3.62 ✓ |
| se_flow 24-47h (sanity) | +7.28% | +14.44% | +11.30% | +7.35% | +4.41% | 0.00 / +9.14 |

Un-skipped fresh negatives beyond these: none material. Skipped cells (calm 24-47/12-23, sea_breeze 24-47, nw_flow 12-23) still show negative pair-log lift as expected — pair log records the counterfactual regardless of runtime skip.

## Verdict per cell

- **nw_flow 24-47h — NOT skip.** 50d earn +1.75%, halves both positive. 3-day dip against a durably-earning cell. This is exactly the failure mode the v0.6.574 two-window gate exists to prevent.
- **frontal 24-47h — WATCH.** Negative every window (fresh/sust/14d/30d/50d). 14d −4.54% n=186 crosses n≥50 and lift≤−3% ADD thresholds but 50d only −1.26% and halves unstable (+0.38 / −2.74). Not eligible today under the two-window gate. If 50d slides toward −3% and half B stays negative, will surface as CONFIRMED — expect 3-7 days out.
- **pre_frontal 24-47h — NOT skip.** Small fresh dip; 14d/30d/50d all positive.

## Why the aggregate flipped

Pooled fresh (09-11→09-14) shows n_sust=4471 lift=+1.06% vs n_fresh=2580 lift=−2.58%. Driven mostly by nw_flow 24-47h flip (307 rows × ~20pp swing) plus frontal 24-47h contribution (69 × ~5pp). Aggregate is noise-amplified by the 3-day window; the 14d aggregate is +2.3% (walkforward EARN verdict).

## How to apply

- Do not proactively add nw_flow 24-47h skip — 50d halves-stable positive, would revert like v0.6.573 did.
- On 09-17 or 09-18 morning digest, if `nbm_skip_add_audit` promotes `l3_nbm.wg.frontal/24-47h` to CONFIRMED (both windows agree + halves), ship it. Otherwise let the sentry alarm clear itself as fresh window rotates.
- Sentry is doing its job on the aggregate; audit is doing its job on the per-cell filter. This split is working correctly.

## Related

- [[project_09_13_session]] — t 24h HRRR PBL dig, same shape of analysis.
- [[feedback_pooled_n_time_thin]] — pooled n-large ≠ time-robust; sentry's 3d window is time-thin.
- v0.6.574 two-window gate — the discipline that prevents shipping this cell today.

## Scratchpad

Analysis scripts: `wg_l3_dig.py` (per-regime fresh vs sust), `wg_l3_windowed.py` (multi-window with halves). Live in scratchpad only; not runtime scripts.
