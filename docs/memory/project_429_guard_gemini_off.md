---
name: project-429-guard-gemini-off
description: "RESOLVED in v0.6.139 — 429 cooldown in _should_call_gemini is now wrapped in `if GEMINI_ENABLED:`. Groq no longer gated by stale Gemini 429s."
metadata: 
  node_type: memory
  type: project
  originSessionId: d1501df5-ccca-43fa-9f71-7dafb1d5eebe
---

**Resolved.** Fix shipped in v0.6.139. `weather_collector/fetchers/briefing_ai.py` `_should_call_gemini()` now wraps the `last_429_at` cooldown branch in `if GEMINI_ENABLED:` (see comment block referencing v0.6.139). The 30-min `last_attempt_at` throttle stays unconditional — that's a UX choice ("don't churn the headline every 10 min"), now also applied to Groq. Verified 2026-06-21: briefing_cache.json has no stuck last_429_at and Groq refreshes the headline on the normal 30-min cadence.

If GEMINI_ENABLED is flipped back to True, the cooldown logic re-engages automatically.

Related: [[project-gemini-quota-real]] (prior quota incident — different cause, same symptom).
