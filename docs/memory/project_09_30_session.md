---
name: 09-30-session
description: "09-30 session — 2 ships (v0.7.17 wg skip remove, v0.7.18 learned_gbm restore + curate fix after discovering v0.7.15 silent no-op from digest overwrite). v0.7.11 and v0.7.15 verifies still weather-pending."
metadata:
  node_type: memory
  type: project
  originSessionId: d4993092-3414-4b8a-9b6a-9fcd354dc60d
  modified: 2026-10-01T12:18:17.087Z
---

**Ships (chronological):**

1. **v0.7.17 (08:57 EDT)** — l3_nbm skip REMOVE: `wg/nw_flow/12-23h`.
   - `nbm_skip_earning_audit` two-window CONFIRMED: 14d n=952 lift +18.30% (halves +11.25/+27.67), 50d n=3,980 lift +6.90% (halves +7.27/+6.61).
   - Companion `wg/nw_flow/6-11h` held — 50d halves +9.52/+2.11 (h2 decays below +3% threshold).
   - Collector-only ship. Pair-log verify expected ~16:57 EDT when first post-deploy 12-23h lead rows pair; actual verify pending due to pair-log compose lag.

2. **v0.7.18 (19:42 EDT)** — learned_gbm silent-no-op fix.
   - **Discovery:** afternoon pair-log inspection on sr post-cutoff rows showed 97 rows in 2 of the 5 covered cells (se_flow/12-23 n=72, se_flow/24-47 n=25), all stamped `selector_mechanism=band_pool`, NOT `learned_gbm`. v0.7.15 was a silent no-op.
   - **Root cause:** `analysis/l1_learned_selector_curate.py` ran during the 09-30 06:22 digest with `FIELDS = ("t","h")` only — it knew nothing about sr. Regenerated the runtime JSON wholesale with `cells: []`, wiping v0.7.15's manually-populated sr cells. Today's v0.7.17 collector redeploy (08:57) baked the empty JSON live. v0.7.15 had worked for ~19 hours before being wiped.
   - **Fix:** restored the JSON from v0.7.15 commit (1a204c3e). Split curate into `V2B_FIELDS=("t","h")` (logistic, from v2b per-field classifier) and `V5_FIELDS=("sr",)` (GBM, from `l1_learned_selector_curated_v5_candidate.json`). Router-as-authority preserved: ch cells from v5 candidate dropped (ch is handled by ims_threshold).
   - **Recurrence-proofed:** tomorrow's digest will emit the same cells from the v5 candidate — no manual repopulate needed.

**Key lessons documented:**
- [[feedback_auto_curate_wholesale_overwrite]] — a daily auto-curate script that regenerates a runtime JSON wholesale will silently wipe cells for any field it doesn't know about.
- [[feedback_shipped_flag_verify_effect]] — verified the mechanism via pair-log attribution, which is what caught the silent no-op in the first place.

**Digest-triage findings (reviewed, action taken or deferred):**
- cc FRESH FIRE (+700% 3d) — lucky-baseline artifact per daily raw MAE (09-26/27/28 unusually clean), no action.
- pp ANOMALY (+109.9%) — real signal from a wet period; not mechanism-diagnosed, deferred.
- l3_nbm wg calm/24-47 skip-ADD — null (didn't clear 2-window; cell already skipped).
- l3_nbm_fit_by_regime hold→promote — DO NOT ship. Only sr PROMOTE but sr.l3_nbm is HOT in sentry (-24.2%); shipping regime fit on top of HOT layer unsafe.
- wg nw_flow stale-skip REMOVE — split verdict. 12-23h shipped as v0.7.17. 6-11h held.

**Weather-pending verifies (carried over from 09-29):**
- **v0.7.11 sr × nor_easter L3 bypass** — still 0 nor_easter rows post-cutoff. Weather hasn't entered the regime.
- **v0.7.15 sr learned_gbm** — v0.7.18 restored the mechanism. First post-v0.7.18 daylight pair-log rows in the 5 covered cells should stamp `selector_mechanism=learned_gbm`. Verify tomorrow morning after sunrise (~06:30 EDT).

**v0.7.17 verify** — pending as of session end (pair-log compose lag ~4h; earliest meaningful rows at valid_time 20:57 UTC = 16:57 EDT, but pair-log hadn't caught up). Verify tomorrow morning.

**wd dig held** — same nor_easter/L3 circuit-breaker pattern as sr but smaller magnitude; held until sr verifies clean.
