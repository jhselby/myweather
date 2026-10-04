---
name: measure-against-live-stack-baseline
description: "When measuring a candidate correction's gain, use the highest-currently-applied layer for that field as baseline, not the pair log's top-level `forecast` (which is L1 for cloud fields even when L4/Lc are live)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d0ce8e13-443e-4221-9625-a6ecbc9e587f
  modified: 2026-07-21T23:33:17.985Z
---

# Measure against the live-stack baseline, not the pair log's `forecast` field

The pair log's top-level `forecast` and `error` fields for cloud fields
(cl/cm/ch/cc) carry **L1 semantics** — they record the raw HRRR value,
even after L4 and Lc are running in production. Per-layer values live
in separate keys: `forecast_l1`, `forecast_l4`, `forecast_l6` (Lc), etc.

**Why:** For scoring/anomaly-detection purposes, the pair log wants a
stable baseline reference. It logs L1 as `forecast` and each correction
level as its own suffix.

**How to apply:** When measuring a candidate correction's gain vs
production (i.e., "does my Δ actually improve over what users see"),
use the highest currently-applied layer for that field:

- `wd`: L1 only (no correction layers wired)
- `cl`: `forecast_l6` post-Lc-ship (2026-07-17); L1 before
- `cm`: `forecast_l6` post-Lc; `forecast_l3` before (cm is in L3_FIELDS,
  not L4_FIELDS)
- `ch`: `forecast_l6` post-Lc; `forecast_l4` before that (ch in L3+L4)
  Also `forecast_chp` post 07-19 v0.6.358 (ch_persistence_gate)
- `cc`: `forecast_l6` post-Lc; `forecast_l4` before
- `t`: `forecast_l2` (t is in L2 with τ=4h)
- `sr`: `forecast_l5` (Lsr regime-aware solar)

**Real cost of the mistake, 2026-07-20:** the cc-saturation additive
correction Stage 1 script measured Δ = obs - `forecast` (which is L1 for
cloud fields), yielding Δ = −50 to −70pp for ch at fc_cc≥80%. Reported
+40-79% MAE reductions and "80 SHIP cells." Sanity check showed Lc had
already been applying Δ ≈ −60pp on the same rows; the correction was
80% a rediscovery of Lc, not a new signal. Investment wasted:
`h_rh_saturation_stage1.py` script + `<field>_cc_sat_correction_curated.json`
outputs + processor draft plan. See [[project_cc_sat_correction]].

**Pp catch 2026-07-21 was RETRACTED — turned out to be a different class of bug.** Initial finding from `pp_brier_reliability.py` showed L4 vs L1 Brier gap of +6.7% and Production=L1 bit-exact. Looked like the same pattern. Traced to completion: **pp was dropped from L3_FIELDS on 07-04 v0.6.304**, so recent pair-log rows (07-12 → 07-21, 40k+ verified) have L1==L4 bit-exact. Older rows (06-21 era, still in the 30-day retention window) have L1≠L4 from when pp WAS corrected. My script's aggregate over 179k rows was 2/3 historical / 1/3 current — the "gap" was a historical artifact of a dropped correction, not a live rendering bug. Fitter tsd (which uses a shorter recent-only window) correctly showed L1==L4==Production.

**New lesson from that misread (worth remembering separately):** the pair log is a 30-day rolling window. When shipping a correction change (add/drop from L3_FIELDS, τ change, etc.), the log becomes NON-HOMOGENEOUS across the retention window until the pre-change rows fully age out (~30 days). Any aggregate analysis over the full log during that transition period mixes different pipeline states. **Before running a per-layer diff on the pair log, either (a) check whether that field's correction stack has changed in the last 30 days, or (b) restrict the analysis window to the post-change subset.** This is a distinct pattern from the "forecast field carries L1 semantics" issue — different failure mode (my script's data was fine, my interpretation of what the data meant was wrong).

**Fields still confirmed to carry L1/L2 semantics in `forecast`:** cc, cl, cm, ch (per original 07-20 cc-sat catch). Not pp — that was retracted. Not verified for pa.

**Prevention checklist before writing a Stage 1 script for a NEW correction:**

1. What layer(s) already fire on this field? Grep L2_TAUS, L3_FIELDS,
   L4_FIELDS in `decay_apply.py`. Check the Lc SHIP list in
   `weather_collector/data/lc_correction_table.json`. Check for
   field-specific specialists (`ch_persistence_gate.py`, etc.).
2. What forecast_lN keys does the pair log carry for this field? Grab
   a recent non-zero row and inspect.
3. Set the script's baseline to the highest-applied layer's key.
4. If the candidate correction fires on the same rows as an existing
   layer, verify the two aren't measuring the same signal from
   different angles.

## Related

- [[cc_sat_correction]] — the specific finding that surfaced this
- [[stated_intent_vs_code_behavior]] — same class of "verify vs code"
- [[verify_writers_for_read_paths]] — same class of silent-mismatch
