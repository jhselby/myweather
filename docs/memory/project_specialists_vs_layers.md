---
name: project-specialists-vs-layers
description: "Specialist naming convention (Lsr, Lt, etc.) codified 2026-07-04 v0.6.296. Specialists get letter-suffix names describing what they act on; they earn a numbered slot when promoted to core scope and lose it when demoted. Debug page renamed; collector code + frontend JS rename queued for the L5-cloud-saturation ship."
metadata: 
  node_type: memory
  type: project
  originSessionId: 20ea0996-7e2b-434e-a249-5e0a5fcdc5fc
---

## Convention (locked in 2026-07-04)

**Core stack** = numbered layers L1–L{N}. **Universal** corrections — can apply to any field via per-field whitelist. Currently L1 (raw) → L2 (obs blend) → L3 (lead-decay) → L4 (diurnal). L5 slot is currently unused.

**Specialists** = letter-suffix names describing what they act on. **Domain-scoped** by construction — the physics of the correction is inherently bounded to a field type. Currently:
- **Lsr** = synoptic-regime solar correction (was L5). Solar-scoped (single field: sr).
- **Lt** = cove-microclimate temperature correction (was L6). Temperature-scoped (single field: t). Dormant since 2026-07-01 v0.6.276.
- **Lc** = cloud saturation-unbiasing (in-progress, ship next). Cloud-scoped (4 fields: cc/cl/cm/ch) — bounded-percentage saturation is inherent to cloud fields; won't apply to wind/temp/etc.

**Distinguishing rule**: universal vs. domain-scoped, NOT single-field vs. multi-field. Lc hits four fields but is a specialist because the physics is cloud-specific.

**Names are stable across ENABLED state.** A specialist keeps its letter name whether it's on or off. Lsr is Lsr whether firing or gated; Lc will be Lc whether ENABLED=False (as today) or ENABLED=True (as it will be after the 7-day gate on 07-11). Verified in a 2026-07-04 evening conversation where Joe first proposed on/off-drives-numbering, then reverted after seeing it re-introduces the exact bookkeeping-leak-into-terminology problem the scope rule solves. Visual "what's firing this tick" belongs to display state (badges, colors on the debug page), not to the name of the layer.

**Dynamic naming**: a specialist earns a numbered slot when it proves broadly applicable (Lsr → L{N} if it later covers more than one field). A numbered layer loses its number if it demotes to specialist scope. Naming reflects **current architectural fit**, not historical branding.

**Why**: Bookkeeping was leaking into terminology. Calling every field-specific corrector "Layer N" produced misleading peer relationships (L5 vs L4 read as siblings, but L4 was multi-field core and L5 was single-field specialist). New convention makes scope visible in the name.

## Applied 2026-07-04 (v0.6.296)

- `corrections_debug.html`: 120 L5/L6 references renamed to Lsr/Lt. Section headers, TOC, tri-column band, Production Stack, Applicability map, Retired hypotheses, tri-card What's-running list — all consistent. Anchor IDs (`sec-layer5`, `sec-archive-l6`) preserved for URL stability; only display text changed.
- `docs/CHANGELOG.md`: entry documents the reclass.

## Queued (not yet done — do at same time as L5-cloud-saturation ship)

- `weather_collector/processors/solar_correction.py`: comment / docstring L5 → Lsr where appropriate. Stamp key `weather_data["solar_correction"]` can stay (backwards compat with historical pair-log parsers).
- `weather_collector/processors/cove_correction.py`: same for L6 → Lt.
- Frontend JS in `corrections_debug.html` and any card files: `_layersFor()`, `_layerApplied()`, badge strings ("L5 ✓ synoptic" → "Lsr ✓ synoptic"). The frontend rename happens naturally when we add the new L5 badge/line for cloud saturation.
- `analysis/l5_solar_analysis.py`, `analysis/l6_l2_double_counting.py`: filenames stay for git history; internal comments can update opportunistically.

## Related

[[project-correction-stack]] — needs update once the collector-side rename lands. [[project-todo]] — L5 cloud-saturation ship carries the follow-up renames. [[feedback-do-it-right]] — the structural-fix instinct that drove the reclass.
