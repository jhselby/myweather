---
name: project-cl-transition-watch
description: "07-29 daily watch on cl/6-11h [transition] b3 mixture-check DEGRADED verdict. Jumped +137%→+217% in one day. cl has NO correction stack (prod=L1=raw HRRR at every layer per 07-29 pair-log cut) — this is pure raw HRRR bias movement. Watch daily through 08-01. Escalation trigger: 3 consecutive readings ≥+200% → investigate upstream HRRR/open-meteo product notes."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2612e533-b493-4573-96ed-5a4b19d7982c
  modified: 2026-07-29T17:02:03.692Z
---

## Fact

cl/6-11h [transition] b3 in c1_stage4_mixture_check:
- 07-28: +137.2% (nR=516)
- 07-29: +217.4% (nR=556)

Companion cell cm/0-5h [transition] b3 is holding stable (+45→+42%). cl/0-5h [transition] b3 dropped OFF the DEGRADED list between 07-28 and 07-29 — so the movement is concentrated at cl/6-11h.

## Why the watch, not action

Per 07-29 pair-log cut (21d window, top-quartile forecast rows, cl field):
- L1 MAE = L2 = L3 = L4 = prod = 22.1 across all cl cells
- **cl has no active correction stack.** The mixture-check drift is raw HRRR bias movement, nothing MyWeather ships can change.

Per [[feedback_mixture_check_window_semantics]]: the audit's 7v7d window means +217% is fresh-past-week motion, not chronic. Daily 14d confidence fitter is already absorbing it into `c1_confidence_curated_v2.json` — bands widen automatically.

## How to apply

- Check daily digest mixture-check verdict for cl/6-11h [transition]
- STAY IN WATCH if verdict falls back below +200% (weather-transient)
- ESCALATE if 3 consecutive readings ≥ +200% through 08-01: check upstream HRRR / open-meteo status, consider whether c1 curated bands need a larger window than 14d to be stable

## Related

- [[project_cm_investigation_07_28]] — parent investigation, joint hypothesis rejected
- [[project_cm_stage4_degradation]] — the 07-11 HRRR shift precedent (structural upstream change)
- [[feedback_mixture_check_window_semantics]] — how to read the +217% number
