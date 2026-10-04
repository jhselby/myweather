---
name: curated-json-schema-contract
description: "A curated JSON file is a data contract between the analysis script that writes it and the processor(s) that read it. Before overwriting or renaming, grep for readers; if any exist, either match the read schema or update the readers same commit."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ee219fc7-b19d-45bb-958f-2e0e51617443
  modified: 2026-07-25T01:03:40.466Z
---

Every `weather_collector/data/*_curated.json` file is a schema contract between the analysis script that produces it and the processor(s) that read it. The schema includes field names (`status` vs `verdict`), lead-band naming convention (`"0-5h"` vs `"0-5"`), and cell-map structure.

**When a new script writes to a curated JSON path that already exists** or **when renaming/restructuring an existing curated JSON**: `grep` for readers first.

**Why:** 2026-07-24. I wrote `h_cl_persistence_blend_stage2.py` emitting `cell.verdict` + `"0-5"` band names to `cl_persistence_gate_curated.json`. That path was already read by `cl_persistence_short_lead.py` which expected `cell.status` + `"0-5h"`. My commit overwrote the file with a schema the reader couldn't parse. Short-lead was ENABLED=False so no user-visible break — but the contract had silently shifted. I only caught it while doing the Stage 3 wire; a less-attentive read would have shipped the mismatch.

**How to apply:**
1. Before writing a new curated JSON path: `grep -rn "<filename>" weather_collector/processors/ analysis/`
2. If any reader exists, either match its expected schema exactly OR update the reader in the same commit.
3. When renaming a processor module: grep for module name + short-name (e.g. `clp`) + any operator string it registers (gate_firing_log, applied_layer stamps). Update all sites in the same commit.
4. Data contracts include: field names, cell-map keys, enum values (SHIP/MARGIN/SKIP/THIN), lead-band naming convention, layer short-names for pair-log attribution.

## Related

- [[feedback_verify_writers_for_read_paths]] — the symmetric rule for the reader side.
- [[feedback_stated_intent_vs_code_behavior]] — schema drift is one form of doc-vs-code drift.
- [[project_07_24_session]] — the incident.
