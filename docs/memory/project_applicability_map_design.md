---
name: project-applicability-map-design
description: "Agreed 2026-06-29, SHIPPED steps 1-5 on 2026-06-30 (v0.6.260). Each module exposes describe_applicability(); collector assembles weather_data['applicability_map']; debug page renders the global view. Steps 6 (per-layer filtered slices) and 7 (A/B/C section reorg) deferred — category badges in the global map carry the distinction without restructuring. See project_06_30_session for ship details."
metadata: 
  node_type: memory
  type: project
  originSessionId: 19e46001-b953-40c1-a522-231781ec1562
---

## STATUS UPDATE 2026-06-30: SHIPPED THROUGH STEP 5

**Done (v0.6.260):**
- (1) Schema example at `weather_collector/data/applicability_map_schema.json`
- (2) `describe_applicability()` in `weather_collector/processors/decay_apply.py` (L3, L4)
- (3) Same in `solar_correction.py` (L5), `cove_correction.py` (L6), `confidence_layer.py` (C1 with `axes` subkey for the cross-field axes shape)
- (4) Collector wires the four modules after `stamp_cove_correction()` and stamps `weather_data["applicability_map"]` with `generated_at` + `layers` list
- (5) `corrections_debug.html` got a new "Applicability map — what corrections trigger, and why" section between Forecast Accuracy and L1. Render function `renderApplicabilityMap(wxDoc)` reads the block, builds per-layer cards with category badges (general-purpose / specialist / confidence color-coded), tables of (field|axis, triggers when, gated by, current state) rows, and graceful "not available yet" fallback if the collector hasn't shipped the block.

**Deferred (fresh-session work):**
- (6) Migrate each existing L# section to render a filtered slice of the map. Considered for the same ship but decided against: doing it well requires either splitting each L# section's prose into "live state" (filtered slice render) + "methodology" (static prose) or duplicating content. Defer until Section D has had a few days of use and we know what shape works.
- (7) Top-level reorg into A/B/C section headings (general-purpose / specialists / confidence). Decided NOT to do — the category badges in the global map carry the distinction already. Adding section-level dividers to 4,000 lines of HTML is cosmetic chrome. Revisit if a third specialist (L7) lands.

## Original design (preserved below for context)

## Why this exists

The page currently uses "Layer N" as the top-level organizing principle. That worked when every correction was general-purpose. It breaks down now because:

1. **Two categories of bias correction emerged.** L1–L4 are general-purpose (any field can flow through, per-field whitelist controls which fire). L5 (sr-only) and L6 (t-only) are field-specific specialists. Treating them as peers of L2/L3/L4 buries the distinction.
2. **A different category emerged — the confidence layer (C1).** C1 doesn't modify forecast values; it widens or narrows the displayed uncertainty band. Different evaluation metric (calibration, not MAE delta).
3. **Conditional gating is growing.** L3 isn't just "on for ws" — it's becoming "on for ws when fc_ws ≥ 3 mph" (calm-wind gate, v0.6.252). L6 is "on for t under sea-breeze regime; degrading under morning-offshore" (per the 2026-06-29 r5_cove_analysis HOLD verdict). The walk-forward L3/L4 drop-cc gate at 5/7 should be a per-(field, regime, lead_band) whitelist, not a flat drop. The page has no place to surface "for this (field, regime, lead_band) cell, what fires?"

Without a structural fix, every new gate adds a paragraph somewhere. The page becomes unreadable.

## The agreed shape

**Three sections (replacing the current "Layer N" top-level headings):**
- **A. General-purpose bias corrections:** L1, L2, L3, L4. Each section describes algorithm + per-(field, condition) gating + audit. Bookkeeping name L_N stays for stack order.
- **B. Field-specific bias corrections (specialists):** L5, L6, future. Single parent heading. Each named for what it does ("Solar synoptic-regime correction," "Temperature microclimate correction"), not "Layer N." Scales — new specialists land as subsections under this parent, never as a new top-level.
- **C. Confidence layer:** C1. Separate because it's a different category (band, not value).

**Plus a new centerpiece — Section D, the applicability map:**
- A cross-cutting view that answers "for this (field, regime, lead_band) cell, what fires and what does it do?"
- Visualized as a grid or chart — graph with axes showing when each decision point fires.
- This is the load-bearing structural piece. Without it, gating logic for L3 calm-wind lives in one place, per-regime L6 lives in another, and you can never see them together.

## Rendering approach: option 3 (both — global is the source, per-layer is a filtered slice)

- A single data structure defines the applicability map.
- Section D renders the whole thing — the "in one glance" view.
- Each layer section in A/B/C renders its own filtered slice — local context for someone studying just that layer.
- When the gating logic changes, both views update together because they read the same source.

Considered and rejected:
- **Option 1 (per-layer only).** No global view; can't ask "for ws at lead 24h under nw_flow, what fires?" without scanning every layer.
- **Option 2 (global only).** Narrative for a layer gets split across two places — algorithm in the layer section, firing rule in the global map. Bad for someone studying one layer.

## Data source: derived from code, not authored separately

The applicability map MUST be derived from the actual gating code. Authored documentation rots; the project's whole doctrine is "debug page is canon." The day the map disagrees with the code, the page becomes a lie.

This is already the pattern for the simple case — `L3_FIELDS`, `L4_FIELDS`, `CALM_GATE_ENABLED` are constants in `decay_apply.py`; the page reads them via `banner-l3-fields` etc. We're extending the same pattern to richer predicates.

## Implementation pattern: `describe_applicability()` per module → collector assembles → JSON in `weather_data.json`

**Per-module function** (co-located with the gating code so it's hard to drift):
```python
# in weather_collector/processors/decay_apply.py
def describe_applicability():
    return {
        "layer": "L3",
        "name": "Lead-decay correction",
        "category": "general-purpose",
        "fields": [
            {"field": "ws", "fires_when": "fc_ws_post_l2 >= 3 mph",
             "gated_by": "CALM_GATE_ENABLED", "current_state": "calm-wind gate off; firing for all ws"},
            {"field": "ch", "fires_when": "always when L3_FIELDS contains ch"},
            ...
        ],
    }
```

Similar functions in `solar_correction.py`, `cove_correction.py`, `confidence_layer.py`, etc.

**Collector wiring** (each tick, after all gating decisions are made):
- Collector imports `describe_applicability` from each correction module.
- Assembles the union into `weather_data["applicability_map"]`.
- That block lands in `weather_data.json` next to the rest of the snapshot.

**Page rendering:**
- `corrections_debug.html` fetches `weather_data.json` (already does this for current state).
- Reads the `applicability_map` block.
- Section D renders the global matrix; each layer section in A/B/C renders its own filtered slice (rows scoped to that layer).

Considered and rejected:
- **Live Python endpoint** the page calls. More "live" but adds a server endpoint dependency the page doesn't currently have. Static JSON via the existing `weather_data.json` plumbing is simpler and sufficient.

## Open design questions (decide when implementing)

- **Predicate language.** How structured does `fires_when` need to be? Free text is easy to write but hard to query; full structured predicates (`{"axis": "fc_ws_post_l2", "op": ">=", "value": 3.0}`) are queryable but heavier to maintain. Start with free text + a `gated_by` flag pointing at the constant; structure later only if Section D needs to compute on it.
- **What axes does Section D's grid use?** Probably field × regime initially, with lead_band as a third filter; mirror what `l3_regime_lead_analysis.py` outputs.
- **C1 mapping.** C1 doesn't fit the "fires for field X" model cleanly — it fires for axes (transition, post-frontal, etc.) that cut across fields. May need its own sub-shape inside the JSON.

## Implementation order (when ready)

1. Define the JSON schema (a small example file is enough — no code yet).
2. Implement `describe_applicability()` in `decay_apply.py` first — covers L1/L2/L3/L4, the most complex case. If this works, the pattern works.
3. Add to `solar_correction.py`, `cove_correction.py`, `confidence_layer.py`.
4. Wire collector to assemble the union into `weather_data["applicability_map"]`.
5. Build Section D in `corrections_debug.html` reading from that block.
6. Migrate each layer section to a "filtered slice" view, removing the duplicated narrative.
7. (Optional, late) restructure top-level headings into A/B/C.

Step 7 is the user-visible "refactor" Joe was talking about — but steps 1–6 are the load-bearing work. The visible reorg without the underlying data structure would just be re-arranging the same problem.

## Status: not started

Discussed and designed 2026-06-29 in the same session that shipped v0.6.249–v0.6.258. Implementation deferred — Joe was at the end of a tight budget week (96% weekly usage spent) and this is real architecture work that deserves a fresh session.

Companion to [[project-specialists-vs-layers]] (which captures the section-reorg-only piece of this). This memory supersedes that one once implementation starts — the applicability map is the load-bearing piece; the section reorg is supporting structure.

Related: [[project-correction-stack]], [[project-specialists-vs-layers]], [[feedback-regime-lead-band-cross-cut]], [[feedback-debug-page-canon]].
