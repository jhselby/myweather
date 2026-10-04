---
name: feedback-selector-is-primary-name
description: "The layer that picks between HRRR-Prod and NBM-Prod per (field, lead-band) is called the SELECTOR in prose. Router-as-authority is a pivot name. Do not drift to calling the current layer 'router' — an old v0.6.432 router was retired and explicitly replaced by the selector; the naming would collide with the archive."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 393ff97d-5dfc-493b-a2fb-a7e2f400b4b7
  modified: 2026-09-29T16:35:10.386Z
---

# "Selector" is the primary name for the L1 picking layer

**Rule.** In prose, section headings, narrative writing, and cross-references, the layer is called the **selector**. Do not use "router" as a synonym in fresh writing.

**Kept as-is (code-tied, don't rename):**
- File: `l1_selector.py`
- Function: `pick_source()`, `pick_source_with_mechanism()`
- Pair-log fields: `selector_source`, `selector_mechanism`
- UI: "Selector Skill" tile, "Selector" per-field column
- Live tables: `l1_selector_table_curated.json`, `l1_learned_selector_curated.json`
- Analysis scripts: `l1_selector_fit_*.py`, `l1_selector_per_obs_classifier_*.py`

**"Router-as-authority" retained ONLY** as the name of the v0.7.5 *framing pivot* (the design shift where the selector became authoritative over the pool table for covered cells), not as a rename of the layer.

**Why.** The debug archive has a v0.6.432 "L1 router" that was retired 2026-08-19 v0.6.437 and explicitly replaced by the selector. From the archived debug page: "v0.6.432 L1 router retired 2026-08-19 v0.6.437. Superseded by the selector on all counts: wider scope (9 fields vs 3), stronger evidence base (30-day scoreboard vs 14-day, plus 108-day backfill for L3 fit), post-cascade application (all corrections apply first, selector picks last)." Calling the current layer "router" in new writing collides with that retired-router history and would confuse anyone reading the archive.

**Failure mode this rule prevents.** During the 09-29 session, I drifted to calling the selector "router" in prose across multiple memory files, the debug page, and CHANGELOG entries — anchored on the "router-as-authority" pivot name and never noticing the terminology drift. Ended up with the same object called both names in the same document. Reverted in v0.7.14; adopted this rule.

## How to apply

- Writing about the current picking layer? "Selector."
- Writing about the design pivot that changed how the selector's precedence works? "Router-as-authority pivot" (the pivot's name) — but the layer itself is still "the selector."
- Writing about the retired v0.6.432 thing? "L1 router (retired 08-19)" — historical context, don't confuse it with the current layer.
- Referencing a code path? Use the actual code name (`l1_selector.py`, `pick_source()`, `selector_mechanism`).

**Don't rewrite history.** Older memory files, older CHANGELOG entries, and archived debug page sections keep their original wording. The rule applies to *new* writing from 09-29 forward. History is the record of how we talked then; the rule is what we standardize on now.

## Related
- [[project_09_29_session]] — origin session where the drift happened and was corrected
- [[project_router_as_authority_pivot]] — pivot memory (retain "router-as-authority" as the pivot's own name)
