---
name: baseline-is-user-default
description: "Total Lift baseline is \"what the user's default weather app already shows them\" — NBM raw for NBM-scope fields, HRRR raw for HRRR-only fields. Not pooled-min (too generous), not per-row oracle (too strict, no user does that)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db1141ff-d13b-4e67-892c-8549b5624841
  modified: 2026-08-25T18:44:07.376Z
---

Total Lift baseline is **NBM raw** for the 9 NBM-scope fields (t, h, dp, ws, wg, wd, cc, ch, sr), **HRRR raw** for the 5 HRRR-only fields (cl, cm, pp, pa, pr — NBM doesn't publish). This is what any regular weather-app user or Amazon-bought consumer device gets by default (NBM is the NWS backbone).

**Why:** iterated three baselines in one evening (v0.6.477 → v0.6.478). Pooled min(hrrr, nbm) credited us for beating whichever raw wins on average, too generous. Per-row oracle min(|error_hrrr|, |error_nbm|) represented a picker no human has (nobody swaps sources per lead-hour), too strict. NBM raw is what the user actually experiences without us. Joe: "if I went on Amazon and bought a device that shows me the field value, what will that fetch? NBM?" — yes, and that's the honest bar.

**How to apply:** any question about "did we beat the baseline" → use NBM raw where in scope, HRRR raw otherwise. Don't reintroduce fantasy oracles even under the "harshest critic" impulse — harshest ≠ unrealistic. See [[project_08_25_evening_session]].

Related: [[feedback_ratio_over_absolute]], [[feedback_measure_against_live_stack_baseline]].
