---
name: evidence-before-ship-from-hrrr
description: "Never transfer HRRR-side skip/config to NBM (or vice versa) on prior alone. Always grade the transfer against the counterfactual rescore first, ship only cells with 30-day evidence of net-positive lift."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db1141ff-d13b-4e67-892c-8549b5624841
  modified: 2026-08-25T18:44:23.110Z
---

Do not ship HRRR skip topology (or any HRRR-side configuration) into NBM layers as an educated-guess prior without grading it first. Use `analysis/nbm_counterfactual_rescore.py` on 30 days of backstamped pair data — walks per-layer error stamps, picks a different column per row based on proposed skip topology, no re-fitting or re-inference. Ship only cells with net-positive Δ NBM lift on 30-day evidence.

**Why:** on 08-25 evening (v0.6.475/476) transferred HRRR SKIP topology onto three NBM layers as an educated-guess prior (wg L3 8 cells, cc L4 5 cells, chp_nbm ch 10 cells). Rescore verdict: wg L3 net +0.16-0.58% (KEPT); cc L4 wash ±0.11% (REMOVED); chp_nbm ch −1.15% at 24-47h (REMOVED). Two of three buckets would have shipped as no-ops or slight regressions if we hadn't graded. HRRR's error structure is not NBM's; correlation of "hurts here for HRRR" → "hurts here for NBM" is not automatic.

**How to apply:** any future proposal to seed NBM configuration from HRRR analog → run the rescore, keep only evidence-backed cells. Don't lean on "HRRR knows what it's doing" as sufficient reason to ship. See [[project_08_25_evening_session]] for the full trial narrative + [[feedback_verify_completeness_claims]].

Also: the counterfactual rescore is the tool. Any future skip-topology proposal (or L4/L5/chp cascade change) should be graded the same way before landing in curated JSON.
