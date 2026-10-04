---
name: nws-dp-promote-08-31
description: "⚠ SUPERSEDED SAME-SESSION: L1 selector (l1_selector.py) already ships dp/wg/wd/cc to NBM at ≥6h. Selector refit 08-31 10:15 UTC gives dp lift +11/+24/+27% at 6-11/12-23/24-47. My 'NWS-dp promote' was measuring against a prod stack already routing to NBM — the +44.6% Δ_prod is inflated by dp-derived-exclusion arc baseline artifacts. REAL residual finding: selector fits band-level only; regime × band cells where NBM wins under a pooled-HRRR band (ws/sw/24-47h +11%, w/24-47h +16%, calm/24-47h +35%) are masked. Actionable: extend l1_selector_fit to per-regime granularity."
metadata: 
  node_type: memory
  type: project
  originSessionId: 132ee303-a10d-41fa-9c87-55f062f955a8
  modified: 2026-08-31T22:26:05.390Z
---

# ⚠ SUPERSEDED SAME-SESSION — see NEW STATUS below

## NEW STATUS (evening addendum)

**Core claim — "dp is a promote candidate" — was already shipped.** The L1 selector (`weather_collector/processors/l1_selector.py`) is live and wired into `forecast_snapshot.py:916`. Today's refit at 10:15 UTC (30-day, 934K rows scanned, 485K kept) ships:

- dp: hrrr@0-5h, nbm@6-11h (+11.3%), nbm@12-23h (+23.7%), nbm@24-47h (+27.1%)
- wg: hrrr@0-5h, nbm@≥6h (+8/+16/+22%)
- wd: hrrr@0-5h, nbm@≥6h (+6/+10/+7%)
- cc: nbm@all bands (+7/+6/+16/+15%)
- t/ws/h/sr/ch: hrrr@all bands (NBM loses pooled)

My benchmark's "MAE_prod" for dp includes this selector routing. The claimed +44.6% Δ_prod was inflated by baseline window artifacts (dp-derived-exclusion arc 08-25 → 08-31 elevated prod MAE in that window). The selector's own 30-day fit sees +27.1% for dp/24-47h — that's the durable magnitude.

## REAL new finding

**Selector fits at band-level only.** The per-regime × band drill (in the obsolete body below) is not consumed anywhere. Cells where NBM wins under a pooled-HRRR band are MASKED:

- **ws pooled all bands = hrrr wins.** But drill shows halves-stable NBM wins at: sw/24-47h +11.3% (n=1142), w/24-47h +16.1% (n=1080), calm/24-47h +35.1% (n=223), ne/24-47h +19.7% (n=558), sw/12-23h +9.9% (n=609), s/24-47h +8.7% (n=817), sw/6-11h +7.5% (n=327), calm/12-23h +27.1% (n=153).
- **t pooled all bands = hrrr wins.** Drill shows halves-stable NBM win: s/24-47h +21.1% (n=817).
- **wd pooled@0-5h = hrrr wins.** No 0-5h regime cells win NBM. Selector picks HRRR@0-5h correctly.

**Actionable ship proposal: extend `analysis/l1_selector_fit.py` to fit per (field, regime, band).** Same n/lift floors + halves-stability. Runtime `pick_source(field, lead_h, regime)` reads the deeper table. Estimated fresh regime × band signal: ~10 additional halves-stable cells across ws/t at 12-47h leads.

## 08-31 evening addendum #2 — diagnostic built, signal likely pre-refit artifact

Built `analysis/l1_selector_fit_by_regime.py` (diagnostic sibling — imports FIELDS/BANDS/priorities/error-walkers from `l1_selector_fit.py`, writes `analysis/l1_selector_by_regime_report.json`, runtime untouched). Ran both windows:

- **30-day (default):** 8 masked cells (pooled picks HRRR, regime × band halves-stable NBM). Dominated by ws-calm: 24-47h +40.9% n=688 (h1 +46.7 / h2 +33.5), 6-11h +33.8% n=183, 12-23h +33.1% n=340. Plus h/ne_flow/12-23h +31%, ws/nw_flow/12-23h +13%, h/se_flow/24-47h +9.6%, ws/sw_flow/24-47h +7.4%, ws/nw_flow/24-47h +7.0%. `t` — none halves-stable (contra the informal "1 cell" estimate above).
- **7-day slice:** only **1** cell (ch/nw_flow/6-11h +15.5% but halves +53/+8.7, borderline). None of the 30d cells reappear.

**Read:** the 30d window is 96% pre-refit (selector refit landed today 10:15 UTC). The ws-calm signal is almost certainly the same class of pre-refit baseline inflation that superseded the original memo. **RE-CHECK on/after 09-07** with a clean post-refit 30d window. If cells still show halves-stable ≥ +10% on n ≥ 200, extend runtime. Otherwise close as no-residual and this whole workstream retires.

Watch item lives in [[project_todo]] P2 slot 1.

## Also worth checking

- **NWS-gridpoint vs direct-NBM never compared.** L1 selector uses direct-NBM (`nbm_common.py`); my benchmark used NWS-gridpoint (NBM-derived via the NWS gridpoint API). May produce different values at the same (field, time). Bounded audit possible.

---

# ORIGINAL MEMO BODY (obsolete — kept for provenance)

**Context:** `analysis/h_nws_gridpoint_benchmark.py` had been sitting unrun for 13 days since v0.6.431 plumbing shipped 08-18. First read fired today.

## Verdicts (08-31)

| field | n | MAE_nws | MAE_l1 | MAE_prod | Δ_l1% | Δ_prod% | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| t | 12,166 | 1.969 | 1.636 | 1.562 | -20.4% | -26.1% | KILL |
| **dp** | **12,016** | **1.751** | **3.523** | **3.162** | **+50.3%** | **+44.6%** | **PROMOTE** |
| pp | 9,156 | 24.038 | 19.219 | 19.219 | -25.1% | -25.1% | KILL |
| ws | 12,166 | 2.209 | 2.064 | 2.028 | -7.0% | -8.9% | KILL |
| wd | 12,166 | 52.747 | 50.634 | 47.950 | -4.2% | -10.0% | KILL |

## dp drill-down (08-31, n=12,016, 2026-08-18..2026-08-31)

**Halves-stability CONFIRMED — signal grows in late half, not window artifact:**
- A (early, 08-18..08-25): n=6,008, Δ_l1=+40.2%, Δ_prod=+35.5%
- B (late, 08-25..08-31): n=6,008, Δ_l1=+58.0%, Δ_prod=+52.0%

**Quarters — no decay pattern:**
- Q1 (08-18..08-22): Δ_l1=+42.6%
- Q2 (08-22..08-25): Δ_l1=+37.5%
- Q3 (08-25..08-28): Δ_l1=+61.6%  (coincides with 08-25 dp-derived-exclusion arc — L2/prod likely got briefly worse; watch)
- Q4 (08-28..08-31): Δ_l1=+54.9%

**Lead-band cross-cut — all bands ship uniformly:**
| lead-band | n | MAE_nws | MAE_l1 | MAE_prod | Δ_l1% | Δ_prod% | halves |
|---|---:|---:|---:|---:|---:|---:|---|
| 0-5h | 1,630 | 1.433 | 2.830 | **1.385** | +49.4% | **-3.4%** | +36/+58 |
| 6-11h | 1,575 | 1.567 | 3.185 | 2.770 | +50.8% | +43.4% | +38/+60 |
| 12-23h | 3,042 | 1.748 | 3.495 | 3.296 | +50.0% | +47.0% | +39/+59 |
| 24-47h | 5,769 | 1.893 | 3.826 | 3.701 | +50.5% | +48.9% | +41/+58 |

**CRITICAL: at 0-5h, current L2-corrected prod (MAE 1.385) is slightly better than NWS-gridpoint (MAE 1.433).** L2 station-Kalman corrections at short leads absorb the L1 gap. Wire-in shape must be lead-band-gated.

**Regime cross-cut (fixed 08-31, using `state_fc.regime_flow`):**

| regime | n | Δ_l1% | halves (A,B) | notes |
|---|---:|---:|---|---|
| w | 2,015 | +72.4% | +68.6/+75.3 | dominant win, stable |
| sw | 2,300 | +68.9% | +67.6/+70.4 | dominant win, stable |
| nw | 1,236 | +54.1% | +53.6/+54.5 | dominant win, stable |
| n | 1,505 | +40.4% | +48.1/+30.1 | strong win, mild decay |
| s | 1,467 | +35.3% | +43.7/+22.9 | strong win, mild decay |
| ne | 1,128 | +19.4% | +36.7/-5.4 | **halves flipping — SKIP** |
| calm | 516 | +17.5% | +26.9/+4.3 | **stability weak — SKIP** |
| se | 1,220 | +7.9% | +26.8/-9.7 | **halves flipping — SKIP** |
| e | 629 | +3.3% | +2.6/+4.2 | **weak win — SKIP** |

**Regime × lead-band cells with negative Δ (must be skipped):**
- e/12-23h: -76.6% (n=136)
- se/12-23h: -18.0% (n=297)
- se/0-5h: -6.8% (n=172)

**Physical read:** westerly-quadrant flows (w/sw/nw/n) bring drier continental air; NWS-gridpoint dp captures the physics cleanly. Easterly/southeasterly maritime regimes are dominated by Salem-local marine boundary-layer moisture flux that a gridpoint smooths away. `s` regime is transitional (upwind mostly continental in summer) so still wins big.

## Ship plan (recommended)

**Shape: regime-gated + lead-band-gated NWS-dp L1 override.**

- **Ship regimes** (halves-stable big wins): `w`, `sw`, `nw`, `n`, `s`
- **Skip regimes** (halves-flippy or weak): `e`, `se`, `calm`, `ne`
- **Skip lead-band**: `0-5h` for all regimes (L2 station-Kalman wins short-lead everywhere; Δ_prod=-3.4% pooled at 0-5h)
- **In-ship shape:** L1 = `forecast_nws` for the 5 ship regimes at 6h+ leads; L1 unchanged elsewhere. L2 station-Kalman continues to run on top.

**Architectural conflict:** dp is currently Magnus-derived from t + h per [[project_dp_is_derived_no_dp_work]] (softened to "default upstream-first; dp-side live with stated reason" on 08-30). NWS-dp L1 override IS a "stated reason" carve-out — dp-side ship with explicit justification (NWS-gridpoint captures dp physics t+h Magnus can't at 6h+ leads).

**Wire-in touch points to verify:**
1. `l1_selector.py` — does it route dp through Magnus, or is Magnus applied downstream?
2. `forecast_snapshot.py` — where dp L1 gets written per hour.
3. `corrected_hourly.py` — L2 station-Kalman for dp (must remain live at 0-5h).
4. `station_bias.py` — `DEFAULT_L2_TAUS` for dp.
5. Pair-log stamping — ensure `forecast_l1` continues to log the chosen source for provenance.

**Verification gates before ship:**
- Rerun benchmark in 7 days. If halves stay same-sign and Δ_prod ≥ +30% at 6h+ leads, ship.
- Add a small `analysis/nws_dp_regime_backfill.py` to stamp regime post-hoc on the 12,016 rows and re-check the regime cross-cut. If any regime shows Δ_l1 < 0, add a regime skip.
- Halves-stability re-check on 7-day post-fit rows only (avoid warmup artifacts).

## Non-ship for t/pp/ws/wd (pooled)  — but narrow cells ship

**Same-session audit (08-31 evening) drilled regime × lead-band on all KILLED fields. Pooled KILL hides halves-stable win pockets:**

**ws — 5+ halves-stable win cells at 12h+:**
- calm/24-47h +35.1% (n=223), calm/12-23h +27.1% (n=153)
- ne/24-47h +19.7% (n=558)
- **w/24-47h +16.1% (n=1080)** and **sw/24-47h +11.3% (n=1142)** — large-n
- sw/12-23h +9.9% (n=609), s/24-47h +8.7% (n=817), sw/6-11h +7.5% (n=327)

**wd — 5 halves-stable win cells:**
- nw/6-11h +25.7% (n=145)
- calm/12-23h +23.6% (halves +23/+24 very tight, n=153)
- s/24-47h +13.9% (n=817), s/6-11h +9.6% (n=167)
- sw/24-47h +5.8% (halves +5/+5, n=1142)

**t — 1 halves-stable cell:** s/24-47h +21.1% (halves +2/+46, asymmetric — watch)

**pp — pooled KILL confirmed, no narrow wins.** Pirate minutely dominates pp near-term.

**Pattern:** NWS wins concentrate at **12h+ leads** in **westerly-quadrant + calm regimes** (same physical intuition as dp — NBM smooths through diurnal/microclimate noise HRRR-plus-L2 captures well at short leads).

**Extended ship shape (v2):** if the L1 router is being built anyway for dp, add a `(field, regime, lead_band)` → NWS lookup for the ws/wd/t win cells above. Cost is a lookup table; benefit is 5-10 additional field × cell improvements at 12h+ leads. Waits on same 7-day re-check gate as dp.

## Follow-ons

1. ~~**Regime-null investigation**~~ **RESOLVED same session.** Not a bug — my initial drill used wrong key path (`r.get('regime')` instead of `state_fc.regime_flow`). Pair log correctly stamps regime under `state_fc` and `state_obs`. Fixed drill re-run gave the full regime cross-cut above.
2. **0-5h L2-on-NWS test** — measure whether L2 station-Kalman on top of NWS-dp beats current L2-on-L1 at 0-5h. If yes, simpler ship: L1 = NWS-dp everywhere on ship-regimes, no lead-band gate needed. Requires either a shadow-log run (v0.6.431-style plumbing but for L2-on-NWS) or a synthetic recompute in analysis.
3. **Q3 spike watch** — +61.6% in 08-25..08-28 coincides with dp-derived-exclusion arc. Confirm the spike is prod-degradation, not NWS-improvement, so we don't over-promise. Prod MAE was Q3=3.647 vs Q2=2.823 — some prod degradation, but Q4 is 4.363 so the trend is real deterioration in prod, not spike-and-return.
4. **7-day stability re-check** — rerun benchmark 2026-09-07 with 7 more days of data. If ship-regime halves stay same-sign and Δ_prod ≥ +30%, ship.

## Related

- [[project_plan_pipeline_to_good]] — Item 0a benchmark decision (this was the overdue one)
- [[project_dp_is_derived_no_dp_work]] — architectural constraint being softened for this ship
- [[project_08_31_session]] — session narrative
