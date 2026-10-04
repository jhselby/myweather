---
name: gemini-quota-real
description: "GCP project weather-data-493811 was bounced off Gemini free-tier serving by Google's automated abuse system after the v0.6.55 (Jun 9) retry-on-429 bug hammered the API for 8 days. Resolved 2026-06-18 by moving to an entirely new GCP project. Causal chain documented so it isn't re-litigated."
metadata:
  node_type: memory
  type: project
  originSessionId: a2f69a08-a1e1-47a9-8293-e089e7e804e0
---

## Root cause and what actually happened

**v0.6.55 (commit 14c1265, 2026-06-09)** added a "retry once on HTTP 429 or 5xx" branch to the Gemini call in `briefing_ai.py`. The throttle in the same file was keyed on `cached_at` (only updated on success), so once Gemini started 429ing, the throttle never tripped — every 10-min collector tick re-tried Gemini, and each 429 immediately fired a second identical call 5 seconds later. ~100-140 calls/day, ~80% rejected, for **eight days (Jun 11-18)**.

That sustained high-error pattern is exactly what Google's automated quota-abuse mechanism watches for. The consequence: **the entire GCP project `weather-data-493811` ("Weather Data") was kicked off free-tier Gemini serving** and dumped into Tier 1 Prepay with no credits. Not just the API key — the whole project. The 429 body earlier in the day showed `quotaValue: 20` for the free-tier per-model RPD, then later showed "prepayment credits depleted" — different surfaces of the same suppression.

## Resolution (2026-06-18)

- **v0.6.113** (Jun 17): persisted `last_attempt_at` across instance restarts, added a 4h cooldown after any 429. Partial fix.
- **v0.6.126** (Jun 17): removed retry-on-429 entirely. Full fix for the offending code path.
- **New GCP project + new key** (2026-06-18, other session): Joe created a fresh project `gen-lang-client-0122671252` ("WymanCoveWeather20260618"), minted a new API key there, and updated the `gemini-api-key` Secret Manager secret in `weather-data-493811`. The Cloud Function still runs on `weather-data-493811` (collector, GCS, billing all stay there) — only the Gemini API calls use the new project's key. The OLD project's free-tier Gemini access **remains bounced**; don't try to recover it without going through Google support, and don't reuse that old key for anything.

## How to apply

- Never reintroduce retry-on-429 in any provider client (Gemini, Groq, anything else). 429 means "you exceeded quota"; another call seconds later just burns another quota unit, and a sustained pattern of that gets the whole project bounced.
- Don't claim the cap is "20 RPD on flash-lite free tier" generally — it isn't. That number was specific to the bounced project's suppression. The new project has whatever the current free-tier default is.
- The 300-char truncation on the failure-body log hid the actual quota dimension for two days. v0.6.127 bumped it to 2000. Keep it there.
- If briefings ever start 429ing again, check the QuotaFailure `violations` block FIRST (it names the actual quotaId and quotaValue), not the surface message.
- The auth-form switch in v0.6.127 (URL `?key=` → `x-goog-api-key` header) was useful housekeeping (keeps the key out of URL access logs) but **not** the cause of any 429s — I incorrectly chased it as a primary hypothesis. Don't repeat that mistake.

See also: [[project-06-18-session]], [[deploy-sequence]], [[gcs-soft-delete-trap]]
