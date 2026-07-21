# wdp ship — pre-computed exact patches (copy-paste for 07-27+)

**Status:** every patch below verified against live code at 07-21. Anchors are
line numbers as of commit `7d7da66`. If lines drift, grep for the exact
`old_string` — every patch uses text unique enough for grep-and-replace.

**Open decisions resolved:**
- mae_over_time L1_ONLY option: **(a)** — extend L1_ONLY branch inline; also
  add wdp to `PERMISSIVE_LAYER_KEYS` so `buckets[(day, fld)]` has a wdp slot.
- SHIP_EVENTS.wd flip-date: **placeholder `<FLIP_DATE>`** — fill in at ship.

**Order of edits:** 1 → 2 → 3 → 4 → 5 → 6 → 7. Backend first, frontend last.
Single commit. `make deploy-collector` before push per [[feedback_deploy_sequence]].

---

## SITE 1 — `weather_collector/collector.py`

**Insert after line 568** (after the `stamp_wg_residual_persistence` try/except
block, before the "Applicability map" block).

```python
    # wd persistence gate — predicted-transition bypass of L1/L2 for wd.
    # Runs AFTER wind_blend (which produces L2 wind_direction) so wdp
    # overwrites the L2 blend where the gate fires; module preserves the
    # pre-gate array as hourly.wind_direction_pre_wd_gate. ENABLED gated;
    # module still stamps telemetry when False for the 7-day live-layer
    # change gate.
    try:
        from .processors.wd_persistence_gate import stamp_wd_persistence_gate
        stamp_wd_persistence_gate(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  wd persistence gate stamp failed: {redact_secrets(e)}")
```

**Order-check** — grep confirms `wind_blend` is called at `collector.py:44`
(imported) and used in the run() body earlier. `stamp_wd_persistence_gate`
insertion after `stamp_wg_residual_persistence` (line 568) is well after any
wind_blend invocation. ✓

**Optional applicability-map extension** — add `_da_wdpg` to the imports at
line ~581 and to the `for fn in (...)` tuple at line ~586. Skip if
`wd_persistence_gate.describe_applicability` doesn't exist yet — check first:

```bash
grep -n "def describe_applicability" weather_collector/processors/wd_persistence_gate.py
```

If present: mirror the chp pattern. If absent: skip, wdp still fires; only
the debug-page applicability map section won't get a wdp row.

---

## SITE 2 — `weather_collector/processors/forecast_snapshot.py` (wd layers dict)

**Replace lines 146-149** (the wd entry in the `layers` dict):

```python
        "wd": {"l1": hourly.get("raw_wind_direction", hourly.get("wind_direction", [])),
               "l2": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
               "l3": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
               "l4": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
               "wdp": hourly.get("wind_direction", [])},
```

Also update the comment block at lines 139-145 — replace:
> l3 = l4 = l2 by construction until wd earns a downstream layer.

with:
> l3 = l4 = l2 = wind_direction_pre_wd_gate (L2 blend result). wdp slot holds
> the post-wdp array. `wind_direction_pre_wd_gate` is stashed by
> `wd_persistence_gate.py:56` (PRE_GATE_KEY) BEFORE the gate overwrites
> `hourly.wind_direction`; falls back to `hourly.wind_direction` when the gate
> is disabled or fired on zero cells (identity fallback).

---

## SITE 3 — `forecast_snapshot.py` applied-layer walk

**3a.** Replace `_derive_applied_layer`'s iteration tuple at **line 179**:

```python
        for lk in ("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp", "wdp"):
```

**3b.** Delete the wd skip at **lines 208-210**. Replace this block:

```python
        for field, lyrs in layers.items():
            if field == "wd":
                continue
            applied = _derive_applied_layer(lyrs, i)
            entry[f"{field}_applied"] = applied
```

with:

```python
        for field, lyrs in layers.items():
            applied = _derive_applied_layer(lyrs, i)
            entry[f"{field}_applied"] = applied
```

Also update the doc comment at lines 202-207 — remove the "Skipped for wd
(all layers structurally equal after the l3 rewrite)" sentence; the wd
structural equality no longer holds once wdp writes a distinct value.

---

## SITE 4 — `weather_collector/processors/forecast_error_log.py` (wd pair-log)

**Replace line 208** (the wd-branch layer loop):

```python
                for lyr in ("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp", "wdp"):
```

Circular diff already correct — no other change needed in this branch.

**Also verify** the non-wd branch at line 244 does NOT need wdp — it doesn't
(wdp is wd-only and non-wd rows won't have `wd_wdp` slot). Line 244 unchanged.

---

## SITE 5 — `weather_collector/processors/decay_fit.py` per-layer loops

**5a.** Replace **line 685** area accumulator loop. Grep for the exact tuple:

```bash
grep -n '("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp")' weather_collector/processors/decay_fit.py
```

For each match, extend to:

```python
("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp", "wdp")
```

**Expected match count:** 2 (accumulator ~685, emission ~1162). If grep
returns 0 or >2, STOP — the file has drifted since 07-21 and this patch
needs re-verification.

**No fallback-path change needed** — `decay_fit.py:715` applied_layer fallback
walk is safe to leave alone; every wdp row will carry an explicit
`applied_layer` stamp (Site 3 above), so the fallback never fires for wdp.

---

## SITE 6 — `corrections_debug.html` frontend (5 sub-sites)

### 6a. `_layerApplied()` at line ~3431

**Insert before the final `return false;`**:

```javascript
    // wd persistence gate (wdp) — post-L2 specialist on wd, LIVE <FLIP_DATE>.
    if (layerKey === "wdp") return fieldKey === "wd";
```

### 6b. `LAYER_LINES` at line ~3469 (after the clp entry)

**Insert**:

```javascript
    { key: "wdp", label: "wd persistence (wdp)",            shortLabel: "wd persistence", color: "rgba(180,210,90,1)",     dash: [] },
```

Yellow-green — persistence family (chp/clp are green shades) but distinct.

### 6c. `LAYER_STYLE` at line ~6179 (after the clp entry, before `prod_real`)

**Insert**:

```javascript
    wdp:  { color: "rgba(180,210,90,1)", dash: [], width: 1.25 },   // wd_persistence_gate — intermediate; prod_real is isProd for wd
```

### 6d. `FIELD_LAYERS.wd` at line 6207

**Replace**:

```javascript
    wd: [{key:"raw", label:"Raw"}, {key:"l2", label:"L2 blend"}, {key:"wdp", label:"wd-persist"}, {key:"prod_real", label:"Prod", isProd:true}],
```

(Also update the preceding comment block at 6202-6206 to reflect wdp is now
LIVE and prod_real is isProd for wd — parallel to what v0.6.371 did for the
other 13 fields.)

### 6e. `SHIP_EVENTS.wd` at line ~6255 (inside the SHIP_EVENTS map)

**Insert new entry** (place after `ch:` block, before closing `};`):

```javascript
    wd: [{date: "2026-07-20", label: "L2 blend"},
         {date: "<FLIP_DATE>", label: "wdp ENABLED"}],
```

---

## SITE 7 — `analysis/mae_over_time.py` (L1_ONLY option (a))

**7a.** Extend `PERMISSIVE_LAYER_KEYS` at line 69-74. Replace:

```python
PERMISSIVE_LAYER_KEYS = [("l5", "error_l5"), ("l6", "error_l6"),
                         # v0.6.361: post-Lc specialists — chp (ch_persistence_gate,
                         # ch only) and clp (cl_persistence_short_lead, cl only).
                         # Chart legend shows them as their own lines once a few
                         # days of data have accumulated.
                         ("chp", "error_chp"), ("clp", "error_clp")]
```

with:

```python
PERMISSIVE_LAYER_KEYS = [("l5", "error_l5"), ("l6", "error_l6"),
                         # v0.6.361: post-Lc specialists — chp (ch_persistence_gate,
                         # ch only) and clp (cl_persistence_short_lead, cl only).
                         # <FLIP_VERSION>: wdp (wd_persistence_gate, wd only).
                         # Chart legend shows each as its own line once a few
                         # days of data have accumulated.
                         ("chp", "error_chp"), ("clp", "error_clp"),
                         ("wdp", "error_wdp")]
```

**7b.** Extend the L1_ONLY branch in `compute_fresh_rollup` — replace the
current wd handling (lines 121-127 in the post-v0.6.371 file):

```python
            if fld in L1_ONLY_FIELDS:
                # Fields without a correction stack. `error` in the pair log IS the
                # raw-vs-obs metric (circular for wd). Route to the "raw" layer.
                e = r.get("error")
                if e is None:
                    continue
                per_layer["raw"] = e
```

with:

```python
            if fld in L1_ONLY_FIELDS:
                # Fields without an L2/L3/L4 correction stack. `error` in the pair
                # log IS the raw-vs-obs metric (circular for wd). Route to "raw".
                # Post-wdp: also read error_wdp so the specialist line appears
                # on the wd accuracy chart. Sample-comparable to raw because wdp
                # rows always carry `error` too.
                e = r.get("error")
                if e is None:
                    continue
                per_layer["raw"] = e
                e_wdp = r.get("error_wdp")
                if e_wdp is not None:
                    per_layer["wdp"] = e_wdp
```

**7c.** No prod_real change needed — v0.6.371's `prod_real` accumulator is
independent of the L1_ONLY branch and reads `error_{applied_layer}` per row.
Once Site 3 stamps `wd_applied="wdp"` on gate-fired cells and `"l1"` (or
"l2" — see below) elsewhere, prod_real populates for wd automatically.

**7d note on wd applied_layer semantics** — the `_derive_applied_layer` walk
returns the DEEPEST layer whose value differs from the prior layer. Post-Site 2:
- On gate-fired cells: l1 → wind_direction_pre_wd_gate at l2/l3/l4 → wind_direction at wdp.
  Walk stamps `"wdp"` if wdp differs from pre-gate; otherwise stops at earlier.
- On non-fired cells: `wind_direction == wind_direction_pre_wd_gate`, so walk stops
  at whichever of l1/l2/l3/l4 last changed. Since L2 = pre-gate on wd, if L2
  blend actually blended obs, walk stamps `"l2"`; if calm-floor skipped, stamps
  `"l1"`.

That's the desired behavior — Prod tracks the "real" applied layer per row.

---

## VERIFICATION SNIPPETS (post-deploy, within 30 min of ship tick)

### Verify gate is firing:
```bash
curl -s https://data.wymancove.com/weather_data.json | jq '.wd_persistence_gate'
```
Should show `{"enabled": true, "persistence_value": <deg>, "fires_by_band": {...}}`
with non-zero counts.

### Verify applied_layer stamps:
```bash
curl -s https://data.wymancove.com/forecast_log.json | python3 -c "
import sys, json
d = json.load(sys.stdin); s = max(d['snapshots'], key=lambda x: x['run'])
stamps = [h.get('wd_applied') for h in s['hours'][:24]]
from collections import Counter
print('wd_applied first 24 leads:', Counter(stamps))"
```
Expect a mix of `wdp` and `l2`/`l1` — pure `l1` means gate never fired,
pure `wdp` means gate fired on every cell (probably a bug).

### Verify per-layer wdp slot in snapshot:
```bash
curl -s https://data.wymancove.com/forecast_log.json | python3 -c "
import sys, json
d = json.load(sys.stdin); s = max(d['snapshots'], key=lambda x: x['run'])
h0 = s['hours'][0]
print({k: h0.get(k) for k in h0 if k.startswith('wd_')})"
```
Should show `wd_l1, wd_l2, wd_l3, wd_l4, wd_wdp, wd_applied`.

### Verify Fitter picks it up (after next :05/:15/…/:55 Fitter tick):
```bash
curl -s https://data.wymancove.com/time_series_diagnostic.json | jq '.per_layer_mae_by_lead.wd.wdp'
```
Should be an array of ~48 values (nulls at long leads until n≥30 accumulates
per lead).

### Verify prod_real for wd:
```bash
python3 analysis/mae_over_time.py
python3 -c "
import json
d = json.load(open('analysis/output/mae_over_time.json'))
wd = d['series'].get('wd', {})
for lyr in ('raw','wdp','prod_real'):
    days = sorted((wd.get(lyr) or {}).keys())
    print(f'{lyr:9s}  n_days={len(days)}  last={days[-1] if days else None}')"
```
Should show raw + wdp + prod_real all populating for the past ~7 days.

---

## SHIP-DAY CHECKLIST (copy into changelog + tick as you go)

- [ ] `wd_persistence_gate.py:52` — `ENABLED = True`
- [ ] Site 1 — collector.py insert
- [ ] Site 2 — forecast_snapshot.py wd layers dict + comment
- [ ] Site 3 — forecast_snapshot.py walk + wd skip removed
- [ ] Site 4 — forecast_error_log.py wd branch tuple
- [ ] Site 5 — decay_fit.py both loops (grep verifies 2 matches)
- [ ] Site 6a — corrections_debug.html `_layerApplied` wdp branch
- [ ] Site 6b — LAYER_LINES wdp entry
- [ ] Site 6c — LAYER_STYLE wdp entry
- [ ] Site 6d — FIELD_LAYERS.wd rewrite
- [ ] Site 6e — SHIP_EVENTS.wd new entry (FILL IN `<FLIP_DATE>`)
- [ ] Site 7a — mae_over_time.py PERMISSIVE_LAYER_KEYS extended
- [ ] Site 7b — L1_ONLY branch wdp emission
- [ ] Version bump index.html (v0.6.??? → v0.6.???+1, plan v0.6.373 per preflight)
- [ ] `python3 build.py`
- [ ] `python3 -m py_compile weather_collector/collector.py weather_collector/processors/wd_persistence_gate.py weather_collector/processors/forecast_snapshot.py weather_collector/processors/forecast_error_log.py weather_collector/processors/decay_fit.py analysis/mae_over_time.py`
- [ ] Localhost debug page load — wd accuracy card renders without JS errors
- [ ] `make deploy-collector` (FIRST, before push)
- [ ] Wait one tick — verify `weather_data.json` shows `wd_persistence_gate.enabled=true`
- [ ] Manual Fitter kick (`?fit=1`) → verify tsd has `per_layer_mae_by_lead.wd.wdp`
- [ ] `git add … && git commit && git push`
- [ ] Post-push: run all 4 verification snippets above
- [ ] Changelog entry
- [ ] Update `project_todo.md` (Lc/chp/wd L2/ws L3 watches ticking; add wdp watch entry through <FLIP_DATE>+14)

---

## KNOWN RISK POINTS (things to double-check before shipping)

1. **Site 2's `wind_direction_pre_wd_gate` fallback path** — if wdp is
   ENABLED but the persistence source is missing (`current.wind_direction`
   unset), `stamp_wd_persistence_gate` no-ops and never sets the pre-gate
   key. `hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", []))`
   handles that — but verify the wd_persistence_gate module's no-op path
   doesn't set `hourly.wind_direction_pre_wd_gate` to an empty list. Grep
   the module for `hourly[PRE_GATE_KEY] =` and check every branch.

2. **Site 3's applied_layer for wd on non-fired cells** — could stamp `"l1"`
   if the L2 blend also skipped (calm floor). Should be uncommon but not
   wrong. Verify Prod tracks correctly in the first-hour snapshot.

3. **Site 6d's FIELD_LAYERS.wd** — the layersForField filter drops layers
   with <3 non-null days. On flip day, `wdp` has 0 days of history, so the
   Prod line will fall back to L2 for the first ~3 days. Same as chp did
   on 07-19 → 07-22. Not a bug; note it in the changelog so it's not
   mistaken for a wiring miss.

4. **Fitter tsd emission for wd.wdp** — line 1162 loop emits arrays even
   for non-owner rows (all-None). For wd.wdp specifically, ALL wd rows
   are owner rows (wdp is wd-only). So wd.wdp should be a real array from
   day 1. Verify with the snippet under "Verify Fitter picks it up."

5. **Fresh circular_diff usage** — Site 4's line 208 already sits inside
   the wd branch that has `_circular_diff_deg` imported and applied. No
   change needed to error calculation. Sanity-check on first tick:
   `error_wdp` should be in [-180, 180] like the other wd `error_lN`.
