---
name: l4-nbm-cc-drop-prep
description: "09-04 Fri prep for 09-09 NBM skip-table curation session. Recommends DROP l4_nbm cc entirely (kill diurnal correction on NBM cc). Backed by 30d per-cell analysis (n=27,313, 30 regime×band cells) showing l4_nbm cc lift over l3_nbm is only +0.79% pooled — best possible skip-table only reaches +1.38%. Walkforward already proposes DROP; this analysis backs it."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1f984b98-d729-43cb-b74b-2c8735715f86
  modified: 2026-09-04T12:22:09.514Z
---

# 09-09 NBM skip-table curation — l4_nbm cc prep

Written Fri 09-04 as prep for 09-09 curation session. Ships-ready analysis.

## Recommendation

**DROP l4_nbm cc entirely.** Do not carry a skip-table for the layer.

Change: remove `"cc"` from `L4_NBM_FIELDS` tuple in `weather_collector/processors/l4_nbm.py` (leave `"ch"` — its sentry is clean and marginal help is strongly positive). Runtime impact: `cc_l4_nbm` slot no longer written; selector's deepest NBM layer for cc becomes L3_NBM.

## Evidence — 30d per-cell pool (n=27,313)

Aggregate lift comparison (pooled MAE, layer variants vs L3_NBM baseline):

| approach | pooled MAE | lift vs L3 |
|---|---|---|
| L3 only (this recommendation)            | 19.562 | 0.00% |
| L4 ON everywhere (current live behavior) | 19.408 | **+0.79%** |
| Selective skip cells with lift < −3%     | 19.380 | +0.93% |
| Selective skip cells with lift < 0%      | 19.293 | +1.38% |

**Best-case skip-table gets +1.38%; simple DROP loses +0.79%.** Delta ≤ 60 bp on a field with pool-wide MAE 19.5 = doesn't justify the maintenance burden.

## Cell verdicts (30d, requires n≥100)

Clear HURT (lift ≤ −3% on 30d, would go in a skip-table if we kept one):
- calm 0-5h — lift −4.2%, n=167 (thin)
- frontal 24-47h — lift −9.8%, n=258
- ne_flow 6-11h — lift −3.4%, n=252

The 09-03 digest walkforward proposed a different 5-cell hurt set at more severe magnitudes on a shorter window — se_flow 12-23h it saw at −13% (30d shows −1.9%), se_flow 24-47h at −4.8% (30d shows **+1.2% helping**). **Cells flip verdict as the window slides.** That instability is exactly why a skip-table would be high-maintenance for marginal gain.

Helping cells worth noting (so we understand what we're giving up):
- sea_breeze 12-23h +9.3% (n=384)
- ne_flow 0-5h +4.7% (n=219)
- nw_flow 12-23h +4.6% (n=1,273)
- nw_flow 24-47h +4.2% (n=2,365)

These will lose their +4-9% lift; that's already baked into the +0.79% aggregate figure above.

## Why walkforward is right

The walkforward validator's whitelist output at 09-04 morning digest was:

```
l4_nbm: DROP cc
```

This analysis confirms: layer's total marginal contribution is ~1% pool-wide, positive but not durable across cells or windows. Walkforward's DROP verdict is the right call.

## Doesn't cascade — scope is clean

- l4_nbm operates on cc (and ch) directly as an hour-of-day diurnal residual: `cc_l4_nbm = cc_l3_nbm - correction(cc, hod)`.
- cl/cm are NBM-side non-existent (NBM doesn't emit them, per [[project_nbm_cloud_fields_finding]]). No NBM cascade for cl/cm exists.
- The Ccd (cc-from-derivation) layer that overwrites `hourly.cloud_cover = max(cl_l6, cm_l6, ch_l6)` applies to HRRR-side only, per 09-03 investigation ([[project_09_03_session]] — the "l4_nbm cc DROP is REAL, not no-op" finding).
- Dropping l4_nbm cc means the selector's NBM-side cc pipeline ends at L3_NBM; downstream Ccd is unaffected.
- l4_nbm ch stays: sentry marginal help +13.7% → +17.1% (fresh 3d actually improved).

## Ship checklist (for 09-09)

1. Edit `weather_collector/processors/l4_nbm.py`: `L4_NBM_FIELDS = ("ch",)`.
2. `analysis/l4_nbm_fit.py` — verify it still emits cc entries (harmless to keep in curated JSON since the load-time whitelist gates the apply path). Or edit fitter to stop emitting cc — but not required.
3. Update `analysis/runlog/build_executive_summary.py` `KNOWN_LIVE_PIPELINES`? No — this is a scope reduction, not a live-pipeline change; the whitelist audit will surface the change on its own.
4. Bump version, changelog. Analysis-only + collector deploy (l4_nbm.py is a collector processor).
5. Post-deploy verify: `gcloud functions logs read myweather-collector` shows no cc_l4_nbm in the L4_NBM apply loop; next digest's walkforward should show `l4_nbm: (nothing)` — DROP cc satisfied.
6. Selector fit re-runs on next digest → picks L3_NBM for cc where NBM wins; behavior identical for HRRR-picked cc cells.

## Related

- [[09-03-session]] — where the l4_nbm cc DROP was surfaced as REAL (not no-op) and deferred to 09-09.
- [[project_nbm_skip_proposals_review]] — the parent scheduled review.
- [[project_nbm_cloud_fields_finding]] — cl/cm NBM absence.
- [[feedback_pooled_n_time_thin]] — cells flipping verdict week-to-week is exactly the instability that motivates the DROP over skip-table call.
