---
name: project-cm-investigation-07-28
description: "07-28 follow-up on 'cm losing lift for 5 days'. Joint cl/cm high-fc-value transition-regime hypothesis raised then REJECTED on 07-29 evidence. Real signal: fresh HRRR-side degradation on cm/cl top-quartile transition rows within past 7 days; corrections are inert on these cells (cl fully raw; cm's L2/L3 shadow-improve but ENABLED=False pre-08-04). No action — daily 14d fitter absorbs into c1 curated bands automatically. Watch cl/6-11h [transition] daily."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9463fe7b-3db7-4c49-86b6-9979ab35e0e0
  modified: 2026-07-29T17:01:32.472Z
---

## Session-close narrative mismatch

Prior session-close ledger (from 07-28 session log) said:
> "cm has been losing lift for 5 days (was −40% range early July, now −9%) — cm L4 mixture-check DEGRADED at 12-23h + 6-11h per digest."

Post-reboot verification against fresh outputs contradicted both halves:

**Half 1 — "losing lift"**: mae_over_time cache shows recent cm lift (07-25 −0.9%, 07-26 −2.1%, 07-27 −1.1%) is a low-raw-error artifact. Days with raw MAE ~0.5–18 leave less error to remove; days with raw MAE ~40–46 (early July: 07-06, 07-07, 07-08, 07-15, 07-21, 07-22) show −10 to −15% lift. Same corrections, different denominators. Not degradation.

**Half 2 — "L4 mixture-check DEGRADED at 12-23h + 6-11h"**: today's fresh mixture check (`analysis/output/runlog/c1_stage4_mixture_check.log`, ran 06:04Z on 07-28) surfaces exactly ONE cm DEGRADED cell:
- `cm/0-5h [transition]` bin 3 (top forecast-value quartile): +45.3% drift, nC=1146 / nR=313

Not 12-23h. Not 6-11h. The session-close claim was inaccurate.

**Rule reinforced:** [[feedback_verify_completeness_claims]] — session-close ledger claims about ongoing/degrading state need a `git status`-equivalent verify before acting. Especially cross-day narratives.

## The real signal — cl/cm joint transition-top-bin

Same fresh mixture-check surfaces cl in the SAME regime/bin pattern:
- `cl/0-5h [transition]` bin 3: +41.8% drift, nC=1146 / nR=313  ← identical n to cm/0-5h
- `cl/6-11h [transition]` bin 3: +137.2% drift, nC=1215 / nR=516

Cloud fields share pair-log observation rows. The identical nC/nR between cm/0-5h [transition] and cl/0-5h [transition] means it's the same underlying observation set — a joint cl/cm correction misbehaving on **high-forecast-value transition-regime cells** at short lead.

**Hypothesis to check after data thickens** (07-30 or later):
- Is there a shared cloud correction (persistence gate? L3 skip? Lc?) firing on the same (transition, high-forecast) cell for cl and cm?
- Do the two `+42/+45%` cells share a common calibration miss or a common upstream correction?

**Where to look:**
- `cloud_saturation_correction.py` — check whether it targets high-fc-value transition
- ch/cl/cm live gate history — grep `.cache_*_gate_history.json` for recent fires in transition regime
- `analysis/l4_regime_lead_analysis.py` — re-cut cl and cm at lead 0-5h [transition] with fc-value bin

## 07-29 outcome — hypothesis REJECTED

Fresh mixture check (07-29 06:04Z) held the same cells + accelerated cl:

| cell | 07-28 | 07-29 |
|---|---|---|
| cm/0-5h [transition] b3 | +45.3% | +42.3% |
| cl/0-5h [transition] b3 | +41.8% | (dropped off DEGRADED) |
| cl/6-11h [transition] b3 | +137.2% | **+217.4%** |

Ran a targeted pair-log cut on cm/cl top-quartile forecast rows split by stable/transition × regime_obs (21d window). Findings:

- **cl has NO correction stack at any layer.** MAE identical L1=L2=L3=L4=prod at every cell. The +217% mixture-check drift is pure raw HRRR bias — nothing to fix in MyWeather.
- **cm's L2/L3 are stable improvers**, not degraders. L3 shadow-helps ~5-15% across all transition cells but ENABLED=False pre-08-04. Prod=L1 or L2 — corrections are inert at these top-bin cells.
- No MyWeather ship in the last week could have made things worse here since prod = raw HRRR.

**The mixture-check window matters** ([[feedback_mixture_check_window_semantics]]): `RECENT_DAYS=7`, `CALIB_DAYS=7`. Both windows are entirely inside the post-07-11 period. DEGRADED means fresh-within-the-past-7-days movement, not chronic 07-11 lingering. Joe caught this — I initially framed as "same as 07-11, do nothing / re-curate" and both were wrong.

**Action taken:** none structural. Daily 14d fitter absorbs into curated bands automatically. Watch cl/6-11h [transition] b3 daily — three consecutive readings ≥ +200% through 08-01 would warrant a bigger HRRR-side investigation (upstream product notes / open-meteo status).

Related: [[project_ws_recovery_prediction_08_04]] (similar watch pattern), [[feedback_scoreboard_before_healthy]].

## Related

- [[project_stage4_audit]] — the audit this mixture check reads
- [[project_stage4_audit_metric_limitation]] — pa/pp bin-skip class
- [[feedback_verify_completeness_claims]] — reinforced today
- [[feedback_mixture_check_window_semantics]] — the 7v7d framing insight from 07-29
