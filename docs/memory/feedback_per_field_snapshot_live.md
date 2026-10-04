---
name: per-field-snapshot-live
description: "The per-field snapshot table on corrections_debug.html reads live from tsDoc.per_layer_mae_by_lead via renderPerFieldSnapshot() as of v0.6.390a. Never hand-edit the 'vs raw' column."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ee3022f3-1d0e-4e93-abfb-dbc558df1928
  modified: 2026-07-30T22:39:04.753Z
---

# Per-field snapshot 'vs raw' column is LIVE — do not hand-edit

**Rule:** the `<td class="pf-mae" data-field="<key>">` cells in the "Current pipeline state — per-field snapshot" table (corrections_debug.html around line 800-895) are populated at page-load by `renderPerFieldSnapshot(tsDoc, wxDoc)`. Do not put a hardcoded percentage into these cells. If you see one, that's a bug — the JS pulls values from `tsDoc.per_layer_mae_by_lead` (same source as the scoreboard).

**Why:** hand-edited percentages went catastrophically stale during the week of 2026-07-24 to 07-30. cl went from −0.2% (stable) to +65.4% (broken) over 3 days but the snapshot still read "−0.2% flat pre-Lc" because I only refreshed the table during full Rule 5 sweeps. Joe uses that section as his primary daily instrument — he would have caught the Lc collapse ~48h earlier if the section had been live. Trust was damaged; the section was rewired same session (v0.6.390a commit 90130bc).

**How to apply:**
- Adding a new field row: give the "vs raw" cell `class="pf-mae" data-field="<field_key>"` and inner text `—` as placeholder. Renderer fills it. For Brier-scored fields (pp), also add `data-brier="1"`.
- Updating the table for a shipped change: change the Status column (narrative, hand-curated) and the Applied-layers column (structural). Never touch the vs-raw cell.
- If tsDoc doesn't have data for the field, the renderer shows "no data" at 50% opacity — that's the correct behavior, don't hardcode.

**Related failure mode:** the "Stable wins" summary line at the bottom of the table (line ~899) is still hand-curated. It's narrative categorization ("stable wins" / "regressing" / "killed"), not a number readout — so hand-editing is appropriate there, but keep it fresh on every ship that changes a field's live status. If wiring that live too, it'd need semantic categorization logic (thresholds + status-column parsing), which is more work than the numeric snapshot.

## Related

- [[project_lc_regime_conditional]] — the crisis that exposed the staleness
- [[feedback_debug_page_canon]] — corrections_debug.html IS truth; if it's wrong the whole workflow is wrong
- [[feedback_stated_intent_vs_code_behavior]] — same pattern (comment says one thing, code does another)
