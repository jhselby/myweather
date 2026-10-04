---
name: l1-by-regime-walker
description: "v0.6.534/v0.6.535 09-01: L1 selector by-regime walker shipped + corrected same-session with NOT_BEFORE_DATE=2026-09-07 guard (diagnostic's 30d window is 96% pre-refit as of 09-01; contaminated positives would ship spuriously). Real day-1 09-07; earliest wire flip 09-14. Router extension deferred."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9ae209fb-f72d-4e86-b7b4-23bca1282ee6
  modified: 2026-09-01T11:41:16.265Z
---

# L1 selector by-regime walker

## Shipped 2026-09-01 v0.6.534

`analysis/l1_selector_fit_by_regime_walker.py` — 7/7-day cell stability gate on masked NBM-win cells surfaced by `l1_selector_fit_by_regime.py` (diagnostic that already existed).

**Motivation:** the diagnostic flagged 8 cells where NBM Prod beats HRRR Prod (halves-stable, n≥60, lift≥3%) but the pooled-band selector picked HRRR — these are ship-eligible lifts sitting on the floor. Previously no temporal-stability track existed for them.

**Pattern:** clone of `_residual_persistence_walker.py`.
- History cache: `.cache_l1_selector_by_regime_walker_history.json` (30-day retention).
- Runtime JSON: `weather_collector/data/l1_selector_by_regime_walker.json` (no runtime consumer yet — provides the read-shape for the future `l1_selector.py` extension).
- Gate: 7/7 consecutive distinct dates present in `masked_cells`. Flipped cells barred from re-entry without operator review.

## Day-1 masked set (09-01)

| field | regime | band | lift | halves | n |
|---|---|---|---|---|---|
| ws | calm | 24-47 | +41.2% | +47/+34 | 688 |
| ws | calm | 6-11 | +33.6% | +48/+22 | 183 |
| ws | calm | 12-23 | +33.1% | +49/+17 | 340 |
| h | ne_flow | 12-23 | +29.2% | +38/+10 | 325 |
| h | se_flow | 24-47 | +16.8% | +9/+10 | 1,465 |
| ws | nw_flow | 12-23 | +13.0% | +18/+5 | 1,028 |
| ws | sw_flow | 24-47 | +7.7% | +9/+8 | 2,423 |
| ws | nw_flow | 24-47 | +7.3% | +6/+12 | 1,985 |

## Earliest wire flip: 2026-09-14 (post v0.6.535 correction)

## v0.6.535 correction (same session)

Same-session sweep surfaced yesterday's uncommitted `corrections_debug.html` 09-07 calendar entry: the diagnostic's 30d window is 96% pre-refit as of 09-01 (L1 selector refit landed 08-31 10:15 UTC), and today's flagged cells are likely the same pre-refit-baseline artifact class that superseded `[[project_nws_dp_promote_08_31]]`. Walker would have accumulated 7 days of contaminated positives → spurious wire flip on 09-08.

Fix: `NOT_BEFORE_DATE = "2026-09-07"` guard in the walker. Below that date the walker prints a suppression stanza and does not persist to history. Day-1 (09-01) cache + runtime JSON deleted. Real day-1 = 09-07 when the diagnostic's window contains 7d of post-refit data.

Lesson: read uncommitted diffs before shipping downstream work. `git status` on session start showed `M corrections_debug.html` — I skipped over it, and it contained the exact caveat that would have prevented the premature ship.

If all 8 cells stay present in the flagged set for 7 consecutive daily reads (through 09-07), walker verdict flips to `WIRE READY` and the router extension becomes worth building.

## Router extension (deferred)

When walker clears, extend `weather_collector/processors/l1_selector.py` to read `l1_selector_by_regime_walker.json` and override the pooled-band pick to NBM for any `(field, regime, band)` cell where `cleared_for_wire == True`. Cells not cleared, or `flipped_in_window == True`, must not be wired without operator review.

## How to apply

- **On daily digest:** check walker verdict line. `BUILDING — walker at day N/7` = keep waiting. `WIRE READY` = router extension work becomes actionable.
- **Do not build the router extension before day 7 clears** — no signal to route yet.
- **Any FLIPPED cell:** treat as invalidated signal; the diagnostic itself needs re-examination for why the cell dropped out of the flagged set.

Related: [[project_08_31_session]] (evening finding that motivated this), [[feedback_grid_select_halves_stable]] (halves-stability rule the diagnostic already applies), [[feedback_whitelist_promotion_gate]] (7-day pattern this walker inherits).
