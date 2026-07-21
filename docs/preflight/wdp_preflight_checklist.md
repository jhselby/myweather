# wdp (wd_persistence_gate) — pre-flight wiring checklist

**Target flip date:** earliest 2026-07-27 (7-day narrow-promote gate + SHIP cell-set stability)
**Ship version (planned):** v0.6.373 or thereabouts
**Reference ships to mirror:** ch persistence (v0.6.358, 07-19) + chp attribution (v0.6.369, 07-20)

---

## PRE-FLIP PREREQUISITES (do BEFORE flipping ENABLED)

Every site below must land in one atomic ship. Missing any one → wdp gets silently absorbed into another layer or throws at collector time. This is the exact [[feedback_specialist_attribution_wiring]] pattern; two same-day catches on record (Lsr v0.6.249, Lc v0.6.355→356). Don't be the third.

### 1. Collector wiring — CRITICAL, or the gate never fires
- [ ] `weather_collector/collector.py` — add after the `stamp_cl_persistence_short_lead` block (currently ends ~line 556). Template from chp:
  ```python
  # wd persistence gate — predicted-regime-transition bypass of L1/L2 for wd.
  # Runs AFTER wind_blend (L2 circular blend). ENABLED gated ...
  try:
      from .processors.wd_persistence_gate import stamp_wd_persistence_gate
      stamp_wd_persistence_gate(weather_data)
  except Exception as e:
      logging.warning(f"  ⚠  wd persistence gate stamp failed: {redact_secrets(e)}")
  ```
- [ ] Verify order: MUST run after `wind_blend` (which produces `wind_direction` L2 array) — otherwise wdp overwrites, then wind_blend re-writes on top, gate is invisible. Grep `collector.py` for `wind_blend` call and confirm wdp lands strictly after.

### 2. Snapshot capture — wdp value into per-layer stream
- [ ] `weather_collector/processors/forecast_snapshot.py:146-149` — wd layers dict currently:
  ```python
  "wd": {"l1": hourly.get("raw_wind_direction", hourly.get("wind_direction", [])),
         "l2": hourly.get("wind_direction", []),
         "l3": hourly.get("wind_direction", []),
         "l4": hourly.get("wind_direction", [])},
  ```
  wdp writes `hourly.wind_direction` and preserves pre-gate array at `hourly.wind_direction_pre_wd_gate` (wd_persistence_gate.py:56). So the fix is:
  ```python
  "wd": {"l1": hourly.get("raw_wind_direction", hourly.get("wind_direction", [])),
         "l2": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
         "l3": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
         "l4": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
         "wdp": hourly.get("wind_direction", [])},
  ```
  l2/l3/l4 now show the pre-wdp (post-L2) array; wdp shows the post-wdp final. Same pattern as ch line 131-138.

### 3. Applied-layer stamp — walk includes wdp + wd re-enters stamping
- [ ] `forecast_snapshot.py:179` layer walk list — currently `("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp")`. Add `"wdp"`:
  ```python
  for lk in ("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp", "wdp"):
  ```
- [ ] `forecast_snapshot.py:207-212` — wd is currently EXCLUDED from applied_layer stamping:
  ```python
  for field, lyrs in layers.items():
      if field == "wd":
          continue
      applied = _derive_applied_layer(lyrs, i)
      entry[f"{field}_applied"] = applied
  ```
  Delete the `if field == "wd": continue` (2 lines). Or narrow the exclusion (comment referenced "all layers structurally equal after the l3 rewrite" — no longer true once wdp writes a distinct value).
- [ ] After ship: verify `weather_data.forecast_log.snapshots[0]["hours"][i]["wd_applied"]` shows `"wdp"` at cells where the gate fires, `"l2"` elsewhere.

### 4. Pair-log emission — wd branch needs wdp key
- [ ] `weather_collector/processors/forecast_error_log.py:208` — wd branch layer loop already lists chp/clp. Add wdp:
  ```python
  for lyr in ("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp", "wdp"):
      v = target_hour.get(f"{short}_{lyr}")
      if v is not None:
          pair[f"forecast_{lyr}"] = round(float(v), 3)
          pair[f"error_{lyr}"] = round(_circular_diff_deg(float(v), obs_f), 3)
  ```
  (Circular diff already correct for wd branch.)

### 5. Fitter aggregation — same v0.6.369 pattern
- [ ] `weather_collector/processors/decay_fit.py:685` — per-layer accumulator loop `("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp")`. Add `"wdp"`. `error_wdp` is None on every non-wd row → loop no-ops harmlessly.
- [ ] `decay_fit.py:1162` — emission loop, same set. Add `"wdp"`. Non-wd fields emit all-None arrays for wdp (matches how l5/l6 emit for non-owner fields).
- [ ] Note: `decay_fit.py:715` applied_layer FALLBACK walk (for pre-v0.6.269 rows without stamp) — safe to LEAVE ALONE. wdp only starts emitting post-flip; every wdp row will carry an explicit `applied_layer` stamp, so the fallback path never fires for wdp rows.

### 6. Frontend — LAYER_LINES + _layerApplied + FIELD_LAYERS + LAYER_STYLE
- [ ] `corrections_debug.html:3407-3425` — `_layerApplied()`. Add before final `return false`:
  ```javascript
  if (layerKey === "wdp") return fieldKey === "wd";
  ```
- [ ] `corrections_debug.html:3443` LAYER_LINES — add wdp entry after clp:
  ```javascript
  { key: "wdp", label: "wd persistence (wdp)", shortLabel: "wd persistence", color: "rgba(180,210,90,1)", dash: [] },
  ```
  Pick a color that reads as "persistence family" alongside chp (#4ad29a green) + clp (#8cd278 light green) but distinct — e.g. yellow-green.
- [ ] `corrections_debug.html:6207` FIELD_LAYERS.wd — currently `[{raw}, {l2 isProd}]`. Change to:
  ```javascript
  wd: [{key:"raw", label:"Raw"}, {key:"l2", label:"L2 blend"}, {key:"wdp", label:"wd-persist", isProd:true}],
  ```
- [ ] `corrections_debug.html:6178-6180` LAYER_STYLE — add wdp entry alongside chp/clp:
  ```javascript
  wdp:  { color: "rgba(180,210,90,1)", dash: [], width: 1.75 },   // wd_persistence_gate — isProd for wd
  ```
- [ ] `corrections_debug.html` SHIP_EVENTS.wd (~line 6237-6249) — currently absent. Add:
  ```javascript
  wd: [{date: "2026-07-20", label: "L2 blend"}, {date: "<flip-date>", label: "wdp ENABLED"}],
  ```

### 7. mae_over_time — permissive series
- [ ] `analysis/mae_over_time.py:74` PERMISSIVE_LAYER_KEYS. Add:
  ```python
  ("wdp", "error_wdp"),
  ```
- [ ] `analysis/mae_over_time.py:51` L1_ONLY_FIELDS = {"wd"}. **Decision point:** wd is still L1_ONLY today (no L2/L3/L4 stack). After wdp ships, `error_wdp` exists on wd rows but `error_l2/l3/l4` still don't (wd's L2 is the wind_blend circular result stored in `hourly.wind_direction` — no separate `forecast_l2` in the pair log yet, per h_wd_l3_residual_stage0 output only 288 rows have forecast_l2). Two options:
  - **(a)** Keep wd in L1_ONLY; add a wd-branch inside `compute_fresh_rollup` that also emits `raw` (from `error`) AND wdp (from `error_wdp`). Small.
  - **(b)** Promote wd out of L1_ONLY, add a "L1_PLUS_SPECIALIST" tier (raw + wdp; skip if either missing). Cleaner but more infra.
  - Recommend (a). Land wdp as a permissive add on top of the existing L1_ONLY branch — one `if fld == "wd"` block that handles both `raw` and `wdp` emission.

---

## POST-FLIP VERIFICATION (within 30 min of the ship tick)

- [ ] `curl -s https://data.wymancove.com/weather_data.json | jq '.wd_persistence_gate'` — should show `enabled: true`, `persistence_value: <deg>`, non-zero `fires_by_band`.
- [ ] `curl -s https://data.wymancove.com/forecast_log.json | jq '.snapshots[0].hours[0].wd_applied'` — should be `"wdp"` (or `"l2"` if the gate skipped this cell).
- [ ] Manual Fitter kick (`?fit=1`), then check `per_layer_mae_by_lead["wd"]["wdp"]` in tsd — should have non-null entries at leads where wdp fires.
- [ ] Debug page: wd accuracy card renders a new **wd-persist** column showing angular MAE per lead band. wd trajectory chart draws a wdp line as isProd.

---

## 14-DAY WATCH (through <flip-date>+14)

- Expected lift per Stage 2: `−26% sw_flow 0-5`, `−20% calm 24-47`, `−12% se_flow 0-5`. Watch trigger: **any of these composed-gate MAE reductions collapses below −5% over rolling 7d** OR the SHIP cell-set (5 cells today) flips 2+ cells at the weekly Sunday re-run.
- Also watch: precision/recall of the transition-detection gate (60% / 81% at Stage 2). If precision drops below 40%, wdp is firing on non-transitions and re-adding noise.

---

## REVERT PATH

One-line flip: `wd_persistence_gate.py:52` `ENABLED = True` → `ENABLED = False`. Redeploy collector. Applied_layer stamps flip back to l2 within one tick; wdp column in per-band tables stays populated (historical) but stops accumulating new n.

---

## SHIP CHECKLIST (paste into changelog on ship day)

- [ ] All Section 1-7 sites landed in one commit
- [ ] Pre-ship: `ENABLED=True` in wd_persistence_gate.py
- [ ] Version bumped in index.html
- [ ] `python3 build.py`
- [ ] `python3 -c "import py_compile; ..."` on decay_fit.py + forecast_snapshot.py + forecast_error_log.py + wd_persistence_gate.py + collector.py
- [ ] Localhost debug page load — wd card renders without JS errors
- [ ] `make deploy-collector` FIRST
- [ ] Wait for tick → verify weather_data.json shows wd_persistence_gate.enabled=true, fires_by_band non-zero
- [ ] Manual Fitter kick → verify tsd has wdp arrays
- [ ] `git add ... && git commit && git push`
