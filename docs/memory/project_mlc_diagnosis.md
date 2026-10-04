---
name: project_mlc_diagnosis
description: "07-16 MLC collapse diagnosed — real break 06-30 (pre-HRRR), stratum-local (9.8× in-bin vs out-of-bin), likely seasonal. Won't re-arm on HRRR clearing."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f628bfb-c69d-4f01-8ea8-d87eb0bb20d7
  modified: 2026-08-10T14:21:11.496Z
---

MLC in-bin cc bias fresh-per-obs-day trajectory: +42.7 (06-28) → +16.6 (06-30) → +3.9 (07-05) → never above +5 through 07-16. **Real break is 06-30**, not the 07-07 "cliff" reported by `marine_layer_anomaly.py`'s cumulative-window fitter.

Split at 07-04 (cm HRRR-anomaly onset): in-bin Δ = −48.6, out-of-bin Δ = −5.0, ratio 9.8×. Stratum-local, not a global cc shift. Biggest daily step (06-30) predates the HRRR anomaly by 4 days.

Companion signal: `marine_layer_cl_stage1` W29 = −2.98 vs W25–W28 +12/+22/+17/+13. Same-week cl weakening in the same weather pattern points seasonal.

**Why:** Diagnosis was needed because the 07-13 read ([[project_07_13_session]]) flagged the collapse at 07-07 and tentatively linked it to the cm HRRR anomaly (07-04 onset). Getting the causation wrong would have led to "wait for HRRR to clear then re-arm MLC" — which today's data shows is not the correct move.

**How to apply:** Hold `MLC.ENABLED=False` indefinitely. Do NOT expect re-arming when the cm HRRR anomaly clears — different event. If revisiting, treat as a seasonal-gating redesign (train separate biases for cool-season vs warm-season NE-flow morning) rather than a "wait for signal to return" decision.

## 08-10 stale-file trap caught + fixed

Digest was flagging "★ MLC in-bin bias: DECAY — baseline +11.02 → recent -2.96 (Δ -13.98)" every morning. Traced to `marine_layer_anomaly.json` last generated 2026-07-31 — the sentry script had been retired to `.py.skip`, so the file was stale for 10 days. Digest read the same fossil verdict every run.

Fresh run 08-10: verdict **STABLE** (in-bin -0.39 → -6.10, below trigger). No new signal.

**Fix:** un-retired `marine_layer_anomaly.py` — this note explicitly wants daily surveillance for "future ★ = new signal", which requires the actual sentry running. Retirement defeated the watch.

**Rule:** any monitor whose parent memory says "watch for future ★" MUST NOT be retired to `.skip.py`. If it's retired the fossil-JSON keeps re-emitting the same alert. See [[feedback_stale_json_from_retired_script]].

Tool: `analysis/marine_layer_collapse_diagnostic.py` (2026-07-16). Related: [[feedback_fresh_per_day_recompute]], supersedes the 07-13 line in [[project_07_13_session]].

## 07-22 anomaly detector re-alert — SUPPRESS UNTIL ~08-06

**07-22 digest** shows `marine_layer_anomaly` ★ COLLAPSE (baseline +26.44 → recent +3.04, Δ −23.40) prominently in the executive summary. **This is not new signal — it's the same 06-30 break, just now visible in the fixed-window comparison because the 7d recent window has fully rolled past it while the 21d baseline window still includes pre-06-30 data.**

Detector's own recommendation matches: "Flipping MLC.ENABLED=True now would over-correct cc." Consistent with the settled diagnosis.

**Expected re-fire pattern:** ★ COLLAPSE will re-alert daily until the 21d baseline window rolls past 06-30 (approximately **2026-08-06**). Per [[feedback_check_contamination_before_acting]], future MLC ★ alerts before 08-06 should be triaged against this note, not treated as new discoveries.

**Action if the ★ persists past 08-06:** something new. Investigate then.

