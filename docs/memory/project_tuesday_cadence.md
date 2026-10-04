---
name: tuesday-cadence
description: "Joe's Claude weekly usage limit resets on Tuesdays, so Tuesdays are his heaviest shipping days. That's the ONLY Tuesday-specific thing. Fitter runs TWICE DAILY at 03:07 and 15:07 EDT (every day, not Tuesday-only). Do NOT frame Tuesday Fitter cycles as revealing 'aged-in effects' or as more diagnostic than any other day — they're just Fitter cycles that happen to fall on Tuesday."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0a14e1f9-f87a-464e-846e-dcdd5c525ad4
  modified: 2026-07-21T21:57:19.076Z
---

# Tuesday cadence — Joe's weekly limit reset, nothing else

## The only fact

Joe's Claude weekly usage limit refreshes on Tuesdays. That makes
Tuesdays his heaviest shipping days. Nothing else about the pipeline
is staged for Tuesday.

## Fitter cadence (unrelated to Tuesdays)

The Fitter runs TWICE DAILY at 03:07 and 15:07 EDT, every day of the
week (per `collector.py` docstring — "03:07 / 15:07 EDT windows").
`?fit=1` can force an off-schedule run.

Any Fitter cycle can surface aged-in effects from a prior ship. There's
nothing special about a Tuesday Fitter run — the "07-07 Tuesday
15:07 showed t/pr/dp shifts traced to 06-30/07-01 marathon" observation
was one data point, not a systematic pattern. Do not lean on it.

## How to apply

- On Tuesdays: expect ship-heavy sessions from Joe.
- On any day: Fitter runs 03:07 + 15:07 EDT. Look for aged-in effects
  from prior ships in either cycle if surprised by field-level shifts.

## Related

- [[project_correction_stack]] — pipeline architecture.
