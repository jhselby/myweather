---
name: stale-field-classifications
description: "Constant sets like L1_ONLY_FIELDS, L2_ADDITIVE, L2_DIRECT, L3_FIELDS, L4_FIELDS classify fields by which correction layers apply to them. They go stale when a new layer ships for a field but the classifier isn't updated. Downstream code branches off the stale classification and silently ignores the new data. Caught 07-21 (wd L2 shipped 07-20; L1_ONLY_FIELDS unchanged; my mae_over_time accumulator's L1_ONLY branch skipped wd's error_l2 for 24 hours)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0a14e1f9-f87a-464e-846e-dcdd5c525ad4
  modified: 2026-07-21T21:16:23.473Z
---

# Field-classification sets go stale when new corrections ship

**Rule:** Every hardcoded set that classifies fields by which correction
layers apply to them is a coupling point. When you ship a new correction
layer for a field, sweep every classifier that names that field and
update it in the same commit. Otherwise downstream branches silently
route the field through the pre-ship path and ignore the new data.

**Why:** Downstream code often takes different branches based on these
classifications:
- `if fld in L1_ONLY_FIELDS:` — routes fields without an L2+ stack
  through a slim path that reads only top-level `error` (skipping
  `error_l2`, `error_l3`, etc.).
- `if fld in L2_ADDITIVE:` vs `L2_DIRECT` — different apply semantics.
- `if fld in L3_FIELDS:` — governs whether L3 decay applies.
- `if fld in L4_FIELDS:` — governs whether L4 diurnal applies.

When the ship day updates the pipeline but leaves the classifier stale,
the classifier still says "no L2 for this field" and downstream skips
reading its L2 data. Data exists in the pair log; the accumulator
ignores it. No error, no warning — just a missing line on a chart.

**How to apply:**

1. On any ship that adds a NEW correction layer for a field, grep the
   codebase for every classifier set that names fields:
   ```bash
   grep -rn "L1_ONLY_FIELDS\|L2_ADDITIVE\|L2_DIRECT\|L3_FIELDS\|L4_FIELDS\|CIRCULAR_FIELDS" --include="*.py"
   ```
2. For each match, ask: does this set need to change now that <field>
   has a new layer? If yes, update in the same commit as the wiring.
3. Downstream `if fld in <SET>:` branches often go one level deeper
   (skip permissive-layer reads, use different apply math, etc.).
   Sweep those too.
4. Test with a local re-run of any affected script and inspect the
   output shape for the field.

**Real cost caught 2026-07-21 (v0.6.371b):**

- 07-20 v0.6.368a shipped wd L2 blend (`wind_blend.py` circular
  unit-vector). v0.6.367 wired the joiner to emit `error_l2` for wd on
  the same tick.
- `analysis/mae_over_time.py:51` had `L1_ONLY_FIELDS = {"wd"}` — pre-07-20
  correct (wd had no L2+ stack). No one updated it.
- My v0.6.371 ship added `prod_real` accumulator but ALSO passed wd
  through the existing L1_ONLY branch (which reads only top-level `error`,
  never `error_l2`).
- Result: wd L2 data existed in the pair log but was invisible in the
  accuracy-over-time chart. `FIELD_LAYERS.wd` had l2 as isProd → no L2
  data → `layersForField` filtered l2 out (3-day floor) → no isProd line
  → wd chart showed only Raw. Joe caught it as "why doesn't wd have
  Production or L2."
- Fix in v0.6.371b was 5 lines: extend the L1_ONLY branch to also emit
  L2 for wd when `error_l2` is present. Compounding fix (chart renders
  correctly from tomorrow's digest).

**Prevention on the wdp ship (07-27):**

The wdp preflight `docs/preflight/wdp_ship_patches.md` already includes
Site 7 which explicitly extends L1_ONLY_FIELDS-adjacent handling for
`error_wdp`. That preflight was written knowing this pattern — good.
But the general habit isn't yet formalized in the ship-day checklist.

**Suggested addition to the ship-day pattern:** any ship that adds a
NEW correction layer for a field gets an explicit "check classifier
sets" step BEFORE the wiring commit. The grep above is the whole check.

## Related

- [[feedback_specialist_attribution_wiring]] — sibling pattern (13
  attribution sites; miss any and specialist gets absorbed). This is
  the same shape but for read-side classifiers instead of write-side
  attribution.
- [[feedback_measure_against_live_stack_baseline]] — sibling pattern
  where the pair log's `forecast` field carries stale semantics for
  cloud fields + pp. The three form a family: **anything downstream of
  the pipeline that has to know "which layer(s) apply to this field"
  is a coupling point that goes stale when the field's stack changes.**
- [[feedback_verify_writers_for_read_paths]] — the inverse: grep for
  writers before shipping a reader. Same class of silent-mismatch.
