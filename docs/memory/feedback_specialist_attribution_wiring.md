---
name: feedback_specialist_attribution_wiring
description: "When a new specialist mutates a shared hourly array, multiple sites must be updated together or the specialist gets silently absorbed into another layer. Caught THREE times: Lsr v0.6.249, Lc v0.6.355→356 same-day, chp/clp v0.6.369 (backend accumulator gap). Sites list expanded per v0.6.369: Fitter accumulator + emission loops are separate from snapshot/joiner + frontend LAYER_LINES/_layerApplied — all must land together."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 43be4b0e-1ee6-46ca-95b4-e8e62a53c216
  modified: 2026-07-21T00:34:57.601Z
---

**Rule:** Any new specialist that mutates a shared `hourly.<field>` array in-place needs coordinated changes at every attribution site. Missing any = specialist silently absorbed into whichever layer's column downstream defaults to.

**Why:** Users see "L4 is winning" (or "Lc is winning") when actually the specialist is doing the work. Post-ship watches read the wrong series. Breaks trust in the whole per-layer decomposition.

**How to apply:** ship every site in one commit, in this order — collector → snapshot → joiner → Fitter → frontend. Verify with the curl snippet below on the first tick after deploy. If you can't do them all today, at least stamp a TODO in the specialist module's docstring pointing at this memory.

---

**The sites** (as of v0.6.369 — the list grew when Fitter aggregation gaps were found separately from snapshot/joiner gaps):

**Specialists that fit into an existing numbered slot (l5, l6) — Lsr, Lc pattern:**

1. **`weather_collector/processors/forecast_snapshot.py`** — for each field the specialist touches, change `"l4":` from `hourly.get("<key>", [])` to `hourly.get("<key>_post_l4", hourly.get("<key>", []))` (pre-specialist value; falls back to live when specialist disabled), and add a new `"l5":` or `"l6":` key holding the post-specialist live array. Slot choice: `l5` if it's the first specialist for those fields, `l6` if `l5` is claimed. Joiner + Fitter iterate `("l1","l2","l3","l4","l5","l6")` so both slots flow through automatically.

2. **`corrections_debug.html` `LAYER_LINES` array** (near `renderAccuracySection`) — add or repurpose the l5/l6 entry with the specialist's display label, short label, and color.

3. **`corrections_debug.html` `_layerApplied(layerKey, fieldKey)`** — return `true` for the specialist's slot only on the fields it actually applies to. Example: `if (layerKey === "l6") return ["cc","cl","cm","ch"].includes(fieldKey);`.

4. **`corrections_debug.html` badges block** (near the `Lsr ✓ synoptic` badge in `renderAccuracySection`) — add the specialist's badge for its owner fields.

**Specialists with their OWN attribution key outside l1..l6 — chp/clp/wdp pattern (v0.6.361 onward):**

Everything above PLUS the Fitter no longer iterates the specialist's key by default — must be added explicitly:

5. **`weather_collector/processors/forecast_snapshot.py` applied_layer walk** (~line 179) — the `_derive_applied_layer` walk list must include the specialist's key at the end. Currently `("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp")`. Order = pipeline order; specialists that run last walked last so `applied_layer` stamps them when their value differs from the prior layer.

6. **`weather_collector/processors/forecast_snapshot.py` field layers dict** — the specialist gets its own key alongside l1..l6 (e.g. line 138: `"chp": hourly.get("cloud_cover_high", [])` — points at the post-specialist live array; the numbered slots point at pre-specialist snapshots like `cloud_cover_high_post_lc`).

7. **`weather_collector/processors/forecast_error_log.py`** (~line 208, 244) — pair-log emission loop over layer keys must include the specialist. Currently `("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp")`. Adds `forecast_<key>` + `error_<key>` per pair row.

8. **`weather_collector/processors/decay_fit.py:685`** — per-layer accumulator loop must include the specialist. Currently `("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp")`. Rows without `error_<key>` no-op harmlessly.

9. **`weather_collector/processors/decay_fit.py:1162`** — per-layer emission loop must include the specialist. Same set as #8. Irrelevant fields emit all-None arrays (matches how l5/l6 already work for non-owner fields).

10. **`corrections_debug.html` `LAYER_LINES`** — add specialist entry with its own color (chp/clp are shades of green — persistence family). Frontend filter (#3 above via `_layerApplied`) narrows to owner field.

11. **`corrections_debug.html` `_layerApplied`** — add branch like `if (layerKey === "chp") return fieldKey === "ch";`.

12. **`corrections_debug.html` `FIELD_LAYERS`** — the per-field accuracy-over-time chart config. Specialist that supersedes L4 is marked `isProd:true` in the field's entry.

13. **`analysis/mae_over_time.py:74` `PERMISSIVE_LAYER_KEYS`** — add `("<key>", "error_<key>")` so the over-time chart picks up the specialist's daily-bucketed MAE.

**How to detect the bug in-flight:** post-flip, check a live snapshot from `forecast_log.json`:

```
curl -s https://data.wymancove.com/forecast_log.json | python3 -c "
import sys, json
d = json.load(sys.stdin); s = max(d['snapshots'], key=lambda x: x['run'])
h0 = s['hours'][0]
for f in ('cc','cl','cm','ch'):  # or whatever fields the specialist touches
    print(f, {k: h0.get(k) for k in h0 if k.startswith(f+'_')})"
```

Look for the specialist's slot key (`<field>_l6` etc.) and that `<field>_applied` picks it when the specialist fires. If `<field>_l4` still shows the post-specialist value or the slot key is absent, the wiring is incomplete.

**History of catches:**

- **Lsr v0.6.249 (2026-06-28)** — initial ship absorbed Lsr into the L4 column for sr. Fix preserved `direct_radiation_post_l4` + added `sr_l5` to the snapshot writer + LAYER_LINES + `_layerApplied`. (Numbered-slot pattern, sites 1-4 above.)
- **Lc v0.6.355 → v0.6.356 (2026-07-17, same day)** — flipped at 15:19; Joe noticed at ~16:30 that the per-band cc card still showed `L2 n/a · L3 off · L4 ✓` with no Lc column. Same shape as Lsr. Fixed as v0.6.356 within the hour. (Numbered-slot pattern.)
- **chp/clp v0.6.361→v0.6.369 (2026-07-19 → 07-20, 1-day gap)** — different shape. chp/clp ship in v0.6.358/v0.6.361 with their own attribution keys (not l5/l6 — they're POST-Lc specialists so they get keys like `chp`/`clp`). Sites 1-4 landed on ship day. But the Fitter's per-layer accumulator (`decay_fit.py:685`) and emission loop (`:1162`) iterated only `("l1"..."l6")` — missing sites 8 + 9 in the list above. Pair rows carried `error_chp` + `error_clp` correctly, forecast_snapshot's applied_layer walk (site 5) included them, Production series read them correctly via `applied_layer`-stamped per-row aggregation — but they were **invisible as their own per-layer MAE series** in tsd. Caught day 2 of the 14-day watch. Fixed v0.6.369 with sites 8-11 (+ 12-13 as follow-ups). Key lesson: when specialists ship with their OWN attribution key (not a numbered slot), Fitter code paths need explicit extension — they DON'T inherit the l1..l6 iteration.

**Watch for**: next specialist candidates are wdp (wd_persistence_gate, earliest 07-27 flip) and any post-Lsr sr specialist. Preflight for wdp at [docs/preflight/wdp_preflight_checklist.md](../../../../Documents/myweather/docs/preflight/wdp_preflight_checklist.md) enumerates all 13 sites — read that on flip day, not this memory.
