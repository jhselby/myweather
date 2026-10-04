---
name: feedback-refresh-current-state-before-defending
description: "When Joe probes a recommendation, refresh the actual current-state data before defending it. Data can be older than the recommendation depends on — a stale metric file almost cost a full day of degraded user forecasts on 08-21."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3686728f-c756-4644-9af6-ccbb2487150d
  modified: 2026-08-22T00:37:59.844Z
---

# Refresh current-state data before defending a recommendation

**Rule:** When Joe pushes back on a recommendation with a probing question, the FIRST thing to do is refresh the underlying data the recommendation depends on. Only THEN decide whether to hold the position or revise.

**Why:** Metric files can be hours or a day stale. A recommendation built on stale data may look defensible until the fresh data shows a completely different picture. Defending a stale-data recommendation is worse than saying "let me refresh first."

**How to apply:**
- If the recommendation rests on a specific JSON file / analysis output / scoreboard, check its `generated_at` (or file mtime) before defending.
- If it's older than the events it should reflect (recent ships, deploys, config changes), re-run the generator first.
- Then re-answer using the fresh numbers. The answer may not change — but if it does, you catch a mistake before shipping the recommendation.

## The 08-21 dp incident (source of this rule)

- Recommended holding on "option 3: drop dp from L3_NBM_FIELDS" in favor of "option 2: skip cells at 0-5h only" because "user impact at 0-5h is zero — selector picks HRRR there."
- Joe probed: "are you saying 3 because that's what you expect the data to do?"
- I switched to option 2 based on the probe alone, without refreshing per_field_scoring.
- After landing v0.6.463 (option 2 skip cells), Joe asked "how come the current scores are the way they are." I finally re-generated per_field_scoring, which was 14 hours stale.
- Fresh data showed dp Prod=2.895 vs L1sel=1.619 at the NBM-picked leads 6-47h — **244% worse than raw NBM**. Option 3 was the correct call all along; option 2 only covered the band where the damage wasn't reaching users.
- Result: shipped v0.6.465 (option 3 belatedly). Users had a day of degraded dp 6-47h forecasts that could have been prevented if I'd refreshed per_field_scoring when Joe first probed.

## When it applies

- Any pushback like "are you sure?", "why that?", "are you saying that because [X]?"
- Any recommendation that reads "user impact is zero" or "the data shows Y" — verify the data source is fresh, not from a run earlier in the session.
- Especially critical when today has shipped code that changes what data is generated (F6 changed writeback; per_field_scoring measured pre-F6 behavior at 10:00 UTC).

**Rule of thumb:** if it takes <30 seconds to re-generate the metric, always do it before answering a probe.
