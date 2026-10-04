---
name: project-l1-static-blend-v076
description: "v0.7.6 ship 2026-09-26, PARTIALLY LIVE since v0.7.20 (2026-10-02) — L1 static blender for h and dp with cascade bypass. Universal ω per field (h=0.44, dp=0.27) on 20 curated cells. Two applied cells as of v0.7.23 (2026-10-03): h/nw_flow/24-47 and h/sw_flow/24-47, via the APPLIED_CELLS allowlist; other 18 still shadow. v0.7.21 fixed the verifier measurement trap the flip created."
metadata: 
  node_type: memory
  type: project
  modified: 2026-10-02T14:10:00.000Z
  originSessionId: b263e9cd-d969-4acf-add7-b0c4f9f5625c
---

# L1 static blender — v0.7.6 shadow ship (2026-09-26)

## 🚨 Status — PARTIALLY LIVE (updated 2026-10-02)

**v0.7.20 flipped the first cell: `h/nw_flow/24-47` only.** n=436 (gate min_n_rows=400, crossed 10-02), lift +35.5%, halves 38.7/33.9 — tightest spread of the nine SHIP-READY cells that day. Deployed rev `00606-mak` 08:33 EDT, verified firing on the 08:57 tick (9 applied rows, leads 24-29 + 43-45, blend math exact). Firing is intermittent — only 1 of 5 ticks had nw_flow at 24-47h.

Mechanism: `ENABLED = True` **plus** `APPLIED_CELLS`, gated by `is_applied()`. All 20 curated cells keep stamping shadow telemetry regardless. Reversal = `APPLIED_CELLS = {}`.

**v0.7.23 (2026-10-03) flipped the second cell: `h/sw_flow/24-47`.** n=830, lift +39.0%, halves 41.8/35.7 (6.1pt spread, tighter than the first flip's). The only unflipped cell clearing `min_n_rows: 400`. Deployed rev `00608-jot` 11:28 UTC, first tick clean. **Inert on arrival** — live regime was nw_flow, so it earns nothing until sw_flow returns. Current state:

```python
APPLIED_CELLS = {"h": frozenset({("nw_flow", "24-47"), ("sw_flow", "24-47")})}
```

Held at that flip: `h/sw_flow/12-23` (n=380 — 20 rows short of the gate, halves 50.6/40.9, next in line), `h/nw_flow/12-23` (n=210, halves 27.2/31.4 — tightest spread on the board but half the gate), `h/sw_flow/6-11` (n=173). The gate was **not** relaxed to chase the concurrent h SUSTAINED FIRE.

**Deliberately did NOT follow the debug page's written plan** (`corrections_debug.html:2320`: strip the curated table to nw_flow/24-47 and set ENABLED=True). That would have destroyed the shadow corpus for the other 19 cells and with it the 10-03 verdict. The allowlist gets the same narrow apply without the loss. v0.7.22 (10-02) rewrote that debug-page block; re-read 10-03, it now correctly describes the shipped allowlist approach.

`dp/nw_flow/24-47` **held** — cleared n (436) and lift (+17.5%) but halves 7.7/42.4 too wide to flip same-day.

**v0.7.21 fixed two traps the flip created** — see [[feedback_apply_flip_invalidates_shadow_verifier]]:
- `_SELECTOR_WRITEBACK` only fired on `selector_source == "nbm"`, so the blend landed in `entry[f]` but not in `hourly["corrected_humidity"]` — would have scored +35% on a value the PWA never served.
- The verifier's `served_mae` came from `row['error']`, which IS the blend once applied → lift exactly 0.0% → the cell would have read HOLD the day after shipping. Fixed by stamping `{f}_preempted_source_shadow` before the overwrite and rebuilding the counterfactual baseline.

**As of session end 10-02, v0.7.21 was NOT deployed and neither ship committed.** See [[project_10_02_session]].

### Shadow retro trajectory (curated cells, n=20)
- 09-28: 0 SHIP-READY / 11 HOLD / 4 KILL / 13 THIN
- 09-29: 2 / 13 / 7 / 7  (post-v0.7.8)
- 10-03: **9 / 11 / 0 / 0** — `dp/pre_frontal/12-23` cleared its KILL; **no KILLs remain**. `h/nw_flow/24-47` held SHIP-READY at +25.9% (n 436→584, halves 33.4/23.2) with `n_applied_rows_7d: 0` and `n_excluded_no_counterfactual_7d: 0` — measurement-trap fix clean, applied rows had not yet closed.
- 10-02: **9 / 10 / 1 / 0** — pre_frontal KILLs collapsed to HOLD; only `dp/pre_frontal/12-23` still KILLs. Other SHIP-READY: h sw_flow 6-11/12-23/24-47, h se_flow 24-47, h nw_flow 12-23, dp sw_flow 12-23/24-47, dp nw_flow 24-47.


## The ship

Commit `25fb14ae` on main. New processor `weather_collector/processors/l1_static_blend.py` + curated table `weather_collector/data/l1_static_blend_curated.json`. Wired into `forecast_snapshot.py` next to the v0.7.0 blender pattern. Stamps `{f}_l1_blend_shadow` on every covered row regardless of the apply gate. **As of v0.7.20 (2026-10-02) `ENABLED = True` with a per-cell `APPLIED_CELLS` allowlist — see Status below. Read the gate via `is_applied(field, regime, band)`, never the bare `ENABLED` flag.**

## Architectural mechanic

Blender output = `ω · forecast_l1 + (1 - ω) · forecast_raw_nbm`. The two RAW L1 forecasts. No L2/L3/L4/L6 correction cascade applied to the blend — the analysis established that cascade on blended L1 hurts more than helps on these fields.

**Different from v0.7.0 blender:** v0.7.0 blends TERMINAL forecasts (HRRR-l4/l6 vs NBM-l3_nbm), keeping the cascades' work. v0.7.6 blends at L1 and BYPASSES cascade. On h and dp, L1-blend-no-cascade beat both terminal-blend and cascade-on-blended-L1 in every mode compared.

## Curated table

```json
{
  "h":  {"omega": 0.44, "cells": [
    ["ne_flow","12-23"], ["nw_flow","12-23"], ["nw_flow","24-47"],
    ["nw_flow","6-11"], ["pre_frontal","12-23"], ["pre_frontal","24-47"],
    ["se_flow","24-47"], ["sw_flow","12-23"], ["sw_flow","24-47"],
    ["sw_flow","6-11"]
  ]},
  "dp": {"omega": 0.27, "cells": [
    ["ne_flow","12-23"], ["ne_flow","24-47"], ["ne_flow","6-11"],
    ["nw_flow","12-23"], ["nw_flow","24-47"], ["pre_frontal","12-23"],
    ["pre_frontal","24-47"], ["se_flow","24-47"], ["sw_flow","12-23"],
    ["sw_flow","24-47"]
  ]}
}
```

Gate: halves-A/B ≥ +5% MAE lift on `error_prod_real`, non-degenerate ω (0.05 < ω < 0.95), min 400 rows/cell.

## Analysis backing (scratchpad, this session)

Six analysis scripts run over 90d pair-log:

1. **`between_vs_outside.py`** — classified rows by whether obs falls between forecasts (blender territory) or outside both (picker territory). h 51%, dp 47% between-fraction. Wind fields (ws/wg/wd) 12-21% between → picker territory.

2. **`blend_seat_comparison.py`** — 9-mode comparison. Blend-at-L1-no-cascade beats live by +20% on h, +30% on dp (halves-averaged). Blend-at-L1-then-cascade was WORSE (cascade fights blended input). Blend-at-Terminal also lost.

3. **`blend_halves_stable.py`** — halves-A/B split reduced the "+20-30%" claim: half-B floors are h +9.1%, dp +23.3%. Real ship expectation. 21 of 42 tested cells cleared halves-A/B.

4. **`blend_deeper.py`** — three hypotheses:
   - Universal regime × band across fields: REJECTED (cell-level noise dominates).
   - Recent 30d vs full 90d: nearly identical STABLE cells (26 vs 27) — ω is time-stable.
   - DIVERGE cells layer decomposition: two flavors — either short-lead cascade genuinely wins, or selector is routing to wrong side (better fix is routing not blender).

5. **`blend_hypotheses.py`** — five hypotheses:
   - Feature-based ω (v0.7.0-style ridge): REJECTED — feature ω loses to static by -3 to -18pp per field. Ridge overfits per-row optimal ω target.
   - Degenerate ω check: 12 cells had ω=0 (all-NBM) — pickers disguised as blenders. Real STABLE non-degenerate cells: h=10, dp=10, t=4, sr=2, ch=6, cc=0.
   - DIVERGE clusters: 0-5h band (18/33 DIVERGE), ne_flow regime (13/33), cc field (18/33) — global exclusion filters.
   - Win rate: top STABLE cells 79-90% row-win rate — decisive, not marginal.
   - Extended fields: h/dp confirmed as primary; t/sr/ch have smaller lift.

6. **`blend_final_batch.py`** — five more hypotheses:
   - Tail compression (p50/p90/p95): dp p95 goes 7.10 → 3.99 (44% catastrophic reduction). h p90 goes 12.99 → 11.16.
   - Blend vs its own components: beats both fc_l1 and fc_raw_nbm on strong cells, ties on marginal.
   - **Universal ω per field: game-changer.** h per-cell 29.1% vs universal 29.0% (identical). dp per-cell 35.2% vs universal 36.7% (universal wins). One ω per field ships instead of one per cell.
   - Cross-field ω sharing: REJECTED. Only 2 of 12 multi-field cells have ω range < 0.15.
   - Blend vs static picker baseline: 10 of 15 cells blend wins; 5 static picker wins — the 5 are candidates for ship-set trimming or accepted as small-loss vs simpler architecture.

## Runtime plumbing

`forecast_snapshot.py` wired at the same seat as the v0.7.0 blender (after the pick/selector decision, before `continue`). Shadow stamp fires unconditionally:

```python
_l1_blend_v = _l1_static_blend.blend_l1(f, _fc_regime_i, _fc_band_i, _l1_v, raw_nbm_v)
if _l1_blend_v is not None:
    entry[f"{f}_l1_blend_shadow"] = _round_for(f, _l1_blend_v)
```

Apply block (gated by `_l1_static_blend.ENABLED`) sits after the v0.7.0 apply block:

```python
if _l1_static_blend.ENABLED and _l1_blend_v is not None:
    entry[f] = _round_for(f, _l1_blend_v)
    entry[f"{f}_applied"] = "l1_blend"
    entry[f"{f}_selector_source"] = "l1_blend"
```

Non-overlapping with v0.7.5 by construction: ims-threshold routes ch, GBM routes sr, blender covers h/dp.

## What's NOT wired yet

User-visible arrays (`corrected_humidity`, `corrected_dew_point`) are NOT overridden by the blender. When `ENABLED=True` is flipped, `entry[f]` and `entry[f_applied]` change but the hourly arrays the PWA reads still show the cascade output.

**Fix location (found post-deploy 09-26):** `forecast_snapshot.py:1211` has `_SELECTOR_WRITEBACK` — an existing loop that overrides `hourly[array_name]` for selector-picks-NBM rows. **Extend that same loop to also override on `entry[f_selector_source] == "l1_blend"`.** Same seat, same shape, no separate `corrected_hourly.py` mod needed. Much less invasive than earlier plan.

For v0.7.7 the change is roughly:
```python
if _h.get(f"{_f}_selector_source") not in ("nbm", "l1_blend"): continue
```
(replace the existing `!= "nbm"` guard.)

## Watch and next steps

- **~10-03: 7-day shadow accumulation gate.** Retro-score `{f}_l1_blend_shadow` vs `error` on live-fresh rows. Halves-stable on fresh corpus. If holds, next-apply-version = ENABLED + corrected_hourly wire + version bump + deploy. (v0.7.7 was used 09-27 for the mechanism-attribution telemetry ship — next apply flip will be v0.7.8+.)
- **Retro scorer available:** `analysis/l1_static_blend_shadow_verify.py` (created 2026-09-27, [[project_09_27_session]]). Reads `l1_blend_shadow` stamp from the local raw pair-log — the GCS-backstamped log is ~3d stale so use raw. Halves-stable A/B verdict per cell + per-field rollup. Emits `analysis/output/l1_static_blend_shadow_verify.{txt,json}` and publishes to GCS. Digest driver auto-picks it up.
- **⚠ Pre-flip TODO: off-curated-table stamping bug.** 12h post-ship read: 78 of 93 shadow-stamped rows landed in `nor_easter` cells NOT in the curated JSON. Root cause — `forecast_snapshot.py:1100` passes its own per-lead `_fc_regime_i` to `blend_l1()` for the stamp decision, but `state_stamp.py` later writes a different `regime_synoptic` into `entry['state_fc']`. Pair-log records the state-stamp regime, not the stamp-decision regime. Consequence: an `ENABLED=True` flip would silently apply blend on cells the halves-stable gate never approved. Fix required before the apply flip — reconcile the two regime resolvers (or route both paths through one). Not a runtime issue while ENABLED=False.
- **If halves-stable fails on fresh:** don't apply. Diagnose regime shift or fit-time bias. The h/dp analysis was on 90d ending ~09-25; fresh 7d might tell a different story.
- **After apply:** measure user-visible lift on debug page trajectory. Expected: h and dp median stack-vs-90d-ref jumps by +10-20pp on covered rows.

## Rejected hypotheses (do not revisit)

- Feature-based ω (v0.7.0-style ridge). Overfits.
- Cross-field ω sharing. Fields want different weights.
- Universal regime rule across all fields. Cell-level heterogeneity too high.
- Rolling refit / recency-tightening. Static ω is time-stable.
- Blender for wind fields (ws/wg/wd). Picker territory, +6-10% blend ceiling.
- Blender for cc. Zero real STABLE cells.

## Related

- [[project_09_26_session]] — session narrative (needs updating with this ship).
- [[project_router_as_authority_pivot]] — v0.7.5, sibling ship 4h earlier.
- [[project_l1_selector_blend_vs_pick]] — the earlier v0.7.0 blender (rolled back v0.7.3 stale-fit). This is a related but architecturally distinct mechanism.
- [[project_l1_blender_stale_fit_audit]] — the discipline that shaped this ship's shadow-first pattern.
- Scratchpad location for the analysis scripts: `/private/tmp/claude-503/-Users-josephselby-Documents-myweather/b263e9cd-d969-4acf-add7-b0c4f9f5625c/scratchpad/blend_*.py`
