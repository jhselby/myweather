---
name: lc-regime-conditional
description: "Regime-conditional Lc pipeline 2026-07-30. Stage 0 SIGNAL / Stage 1 STAGE 1 PROMOTE 92 cells / walk-forward validator (v0.6.389f) revealed VERDICT: FLAT overall (-1.55%) + cl broken under BOTH pooled AND regime-conditional Lc (-22 to -30% vs raw on held-out). cl FULLY REMOVED from Lc via _FIELD_SKIP v0.6.389f. cc/cm/ch keep pooled Lc (all help vs raw held-out +5/+35/+36%). 2-cell cc/ne_flow demote retained. Stage 3 candidate SHIP set is walk-forward-verified 22 cells, NOT Stage 1's 92."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c13f0ec-2762-47f1-aab5-a15c48f08029
  modified: 2026-08-13T12:03:27.274Z
---

# Lc regime-conditional pipeline

## Trigger — 2026-07-30 AM digest read

Joe flagged Overall Prod-vs-Raw regressing from ~−13% (a week ago) to −5.2% (today), cl at +31.5% MAE regression. Trajectory analysis (`mae_over_time.py`):

- cl raw MAE 07-25 → 07-30: 4.29 / 11.26 / 10.15 / 23.21 / 21.18 / **7.29**
- cl l6 MAE (Lc-corrected): 3.36 / 5.22 / 6.07 / 26.88 / **45.23** / **56.96**

Lc went from helping to 8× hurting. Same pattern on cc (raw 7.21 → l6 44.23). cm/ch held.

**Root cause identified via Stage 0:** pooled Lc's shift table is regime-blind. When the regime mix shifts, one regime's over-forecast pattern anchors the pooled shift away from what other regimes need. `analysis/h_lc_regime_stage0.py` bins by (field, regime, bin) and finds 95 ★ cells across all 4 cloud fields with 33 cells where pooled-live shift diverges from regime-conditional truth by ≥8pp.

Specific ne_flow evidence — pooled OVER-corrects:
- cl/ne_flow/80-95: live −61, regime −35 (26pp over)
- cl/ne_flow/95-100: live −58, regime −32 (26pp over) + HALVES-DIVERGE
- cc/ne_flow/50-80: live −27, regime −3 (23pp over) — SKIP-mag verdict per Stage 0
- cc/ne_flow/80-95: live −30, regime −8 (22pp over) — SKIP-Δ verdict

**Not a code change.** Same architectural pattern that failed as MLC (2026-07-16, regime-blind on morning NE-flow) and as ws L2 24h blend (2026-07-28, single τ across regimes). Third instance of "regime-blind bias layer" biting us — see [[project_cm_investigation_07_28]] for the 07-29 rejection of a joint cl/cm hypothesis and pointer to "raw-HRRR-side drift, fitter absorbs" — the fitter absorbs SLOWLY because Lc's shift table refits on a rolling 30d window.

## Pipeline

**Walk-forward validator finding (v0.6.389f 2026-07-30) — CRITICAL:**
`analysis/walkforward_lc_regime.py` train pre-07-20 / test 07-20→07-30 held-out MAE:
- cc: pool -22% helps, reg -30% helps more (pool_vs_raw +5.3%, reg_vs_pool +0.63%)
- **cl: pool HURTS -22.15% vs raw, reg HURTS MORE -30.37%.** Neither architecture fits cl's recent distribution.
- cm: both help ~34-35% (reg flat vs pool -0.22%)
- ch: both help ~36% (reg flat vs pool +0.28%)
- Overall verdict: FLAT (-1.55%). Stage 1's 92 SHIP cells are over-generalized — only 22 actually beat pooled on held-out; 21 lose.

**cl field-kill (SHIPPED v0.6.389f, LIVE):**
`_FIELD_SKIP = frozenset({"cl"})` in `cloud_saturation_correction.py`. cl hourly array untouched; `per_field.cl.field_skipped=True` in telemetry. Removes cl from Lc entirely. Reversibility: remove `"cl"` from the frozenset to re-enable.

**Rolling-window diagnostic result (v0.6.389g `h_lc_rolling_window.py`):**
Swept W ∈ {3, 5, 7, 10, 14, 21, all} days. **No window fixes cl on last 3d held-out** (best W=3d, still −3.7% vs raw). Also exposed cc broken on last 3d under every window (best W=7d, −25.5%). cm+ch survive across all windows. Verdict: shift-table architecture can't handle recent HRRR bias shift with any window length. Rolling window alone is not the fix.

**cc/95-100 bin-skip (SHIPPED v0.6.389g, LIVE):**
Diagnosed cc bleed as bin-concentrated — on 07-30, 99% of cc forecasts landed at 95-100, obs matched at overcast, Lc's −58 shift dragged corrected 90→32 → error ~53. Added `("cc", "95-100")` to unified `_CELL_SKIP` frozenset (universal-regime demote). `_CELL_SKIP` now supports both `(field, bin)` and `(field, regime, bin)` shapes; `_shift_for` checks both. cc/0-5, cc/50-80, cc/80-95 remain alive (except regime-conditional ne_flow demotes retained).

**Current live Lc SHIP surface:**
- cl: off (field-kill)
- cc: 0-5 (all regimes); 50-80, 80-95 (all regimes except ne_flow); 95-100 OFF
- cm: full curated table
- ch: full curated table

**Architectural next step (unshipped) for cl:** shift-table architecture can't distinguish "model over-forecasts overcast" from "model correctly forecasts overcast." Any window length preserves the mistake. Candidates: EMA/Kalman shift tracker OR recent-bias gate on lc_fit. Both multi-day workstreams.

**Ccd (cc from-derivation) SHIPPED v0.6.389j 2026-07-30 ENABLED=False:**
Retires cc's entire Lc surface. `analysis/h_cc_derivation.py` on 123,050 held-out quads (07-01→30): derived-max(cl_l6, cm_l6, ch_l6) beats current cc by **+8.5% pooled MAE**, +5.8% halves-averaged, wins 6/9 regimes. Loses in se_flow (−6.5%, real signal), marginal-loss in unknown/calm. Wins scale with lead (0-5h +1.5% → 24-47h +10.3%). `cc_from_derivation.py` runs after Lc; overwrites `hourly.cloud_cover` with `max(cl, cm, ch)`. `SKIP_REGIMES = {"se_flow", "unknown"}` → Pirate fallback. 7-day live-shadow gate starts today (day 0/7). Earliest flip **2026-08-06**. On flip: cc emergency `_CELL_SKIP` entries become moot (cc/95-100 kill + cc/ne_flow demotes retired same commit). Ccd is robust to cl being off Lc — cm+ch corrections carry the signal.

**Stage 0 — magnitude sweep (SHIPPED v0.6.389d)**
- `analysis/h_lc_regime_stage0.py`
- Verdict: SIGNAL — 95 ★ cells across all 4 fields (cc/cl/cm/ch)
- Divergence table shows 33 cells where pooled diverges from regime by ≥8pp
- Halves stability: 13/204 diverge (time-stable signal)
- Output: `analysis/output/h_lc_regime_stage0.txt`

**Emergency demote (SHIPPED v0.6.389d, same commit)**
- `weather_collector/processors/cloud_saturation_correction.py:_REGIME_SKIP` frozenset
- 4 cells: `cl/ne_flow/80-95`, `cl/ne_flow/95-100`, `cc/ne_flow/50-80`, `cc/ne_flow/80-95`
- `_shift_for()` extended to take `regime` arg; returns `(shift=0, bin, demoted=True)` when tuple hits `_REGIME_SKIP`
- `stamp_cloud_saturation_correction()` reads `derived.state.regime_synoptic` at apply time
- `per_field` telemetry gains `cells_demoted` counter alongside `cells_fired`
- Same shape as v0.6.382t chp emergency demote
- **Bandage lifts when Stage 3 lands** — `_REGIME_SKIP` gets removed then

**Stage 1 — halves-strict fit (SHIPPED v0.6.389e)**
- `analysis/h_lc_regime_stage1.py` — both halves must improve ≥ HALVES_MIN_PCT (stricter than Stage 0's "both positive")
- Chronological halves-split by `obs_time` so recent-anomaly contamination shows up as B < A
- Verdict: STAGE 1 PROMOTE — **92 SHIP cells** across 4 fields (cc:22, cl:29, cm:22, ch:19)
- Emits `analysis/output/lc_regime_curated_stage1.json` — Stage 3 candidate schema:
  ```
  cells[field][regime][bin]: {n, mean_bias, shift, mae_pre, mae_post, improve_pct, halves:{a,b}, verdict}
  pooled_fallback[field][bin]: same shape as live lc_correction_table.json
  ```
- Gate history: `.cache_lc_regime_gate_history.json` (30d retention, 7d flip window)
- Stage 2 walk-forward starts today = **day 1/7 through 08-06**

**Stage 2 — walk-forward stability (day 1/7 through 08-06)**
- Watch SHIP-set stability across 7 daily h_lc_regime_stage1 runs
- gate_clear requires: ≥7 distinct days, no HOLD, no SHIP-set changes, SHIP count > 0
- Jaccard ≥ 0.8 across 7 daily reads (same shape as chp/clp/wdp/dprp gates)

**Stage 2b — walkforward SHIP-set stability gate (SHIPPED v0.6.404 2026-08-13)**
- `analysis/walkforward_lc_regime_ship_stability.py` — parses SHIP cell list from `walkforward_lc_regime.txt`, appends to `.cache_walkforward_lc_regime_ship_history.json`, verdict BUILDING/UNSTABLE/READY over 7d window
- Motivation: Stage 1 `.cache_lc_regime_gate_history.json` ship_count drifted 92→50 over 2 weeks. Before Stage 3 wire, need to confirm walkforward's smaller 16-cell verified set is itself time-stable. Today's walkforward VERDICT PROMOTE +3.06% (16 SHIP / 9 SKIP-regime / 104 flat) is a point read.
- Day 1/7 seeded 2026-08-13. Earliest READY verdict: **2026-08-20**.
- Same 30d retention / 7d window shape as h_lc_regime_stage1.py

**Stage 3 — wire ENABLED=False (pending Stage 2b READY)**
- Extend `cloud_saturation_correction.py` to:
  1. Load `analysis/output/lc_regime_curated_stage1.json` (or move to `weather_collector/data/` first)
  2. Look up cells[field][regime][bin] — apply if SHIP
  3. Else look up pooled_fallback[field][bin] — apply if SHIP
  4. Else no shift
- Remove `_REGIME_SKIP` frozenset (superseded by proper curated table)
- 7-day live-layer flip gate (Stage 4)

## Two-tier apply logic (design intent)

```
def shift_for(field, regime, bin_lab):
    regime_cell = curated["cells"][field].get(regime, {}).get(bin_lab)
    if regime_cell and regime_cell["verdict"] == "SHIP":
        return regime_cell["shift"]
    pooled_cell = curated["pooled_fallback"][field].get(bin_lab)
    if pooled_cell and pooled_cell["verdict"] == "SHIP":
        return pooled_cell["shift"]
    return 0.0
```

Pooled fallback matters because most (field, regime, bin) cells are THIN — only ~40% of the 9×6 grid clears MIN_N=200 per field.

## Related

- [[project_cm_investigation_07_28]] — 07-29 REJECTED joint hypothesis; the "fitter absorbs" claim was too optimistic. Fitter absorbs SLOWLY (30d rolling) and pooled Lc's shape doesn't compensate for regime mix shifts.
- [[project_mlc_diagnosis]] — same architectural pattern (regime-blind bias in cloud layer, seasonal/regime-triggered failure)
- [[project_lc_flip_outcome]] — the 07-17 flip that made this Lc live
- [[project_correction_stack]] — correction stack architecture
- [[feedback_regime_gate_first]] — the framework this pipeline follows
- [[feedback_hypothesis_promotion_pipeline]] — 4-stage discipline
- [[project_cc_is_blend_of_clchcm]] — semantic (cc physically ≈ union of cl/cm/ch) but NOT code (cc from Pirate feed, cl/cm/ch from HRRR); so Lc needs regime-conditional treatment for all four fields independently.
