---
name: feedback-ship-count-by-impact-class
description: "When reporting shipping activity (\"we shipped v0.6.XXX today\", \"N ships this week\"), classify each ship by impact class — skill / maintenance / bleed-stop / miss. Prevents debug-page sweep days and dynamic-gate migrations (which ship neutral by design) from feeling like forecast improvement. Established 2026-08-18 after 6-week audit showed 1.5 skill ships vs. ~30 total ships in that window, with the raw count masking the plateau."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 23b5871a-fdee-47f7-9ac1-9e9135a084ab
  modified: 2026-08-18T14:11:05.401Z
---

Ship count without impact class is a lie. A "3-ship day" that includes 3 debug-page sweeps is not the same as a 3-ship day that includes one skill gain + two bleed-stops.

**Four impact classes:**

1. **Skill ship** — moved measurable user-visible MAE / RMSE / persistence-skill on at least one field. This is the only class that answers "did the forecast get better?"
2. **Maintenance ship** — infrastructure, debug page, sentry, dynamic gate armed neutral, MEMPROBE tweaks, publisher fixes, iOS UI fixes. Necessary work, but not skill.
3. **Bleed-stop ship** — restored a regression back toward baseline (e.g., v0.6.417 L5 solar bias refit stopped sr from bleeding after regime flip). Necessary, but restoration, not new skill.
4. **CLOSED MISS** — investigation that closed without shipping code, OR shipped a scar-tissue removal (field-skip, cell demote) that stopped active damage without adding skill.

**Bar for "skill ship":** persistence skill vs pre-ship baseline improves ≥3% AND regression sentry stays clean on 14-day post-ship watch. If a ship claims skill but numbers wobble around zero, downgrade to maintenance.

**Why this matters:** the 6-week audit on 2026-08-18 found ~30 total ships in the window, of which only 1.5 were skill ships (v0.6.394 Lsb sea_breeze — clear win; v0.6.417 L5 refit — bleed-stop, arguably 0.5). The rest were maintenance or CLOSED MISS. Raw ship count masked the fact that user-visible forecast quality was flat. Impact-class categorization surfaces the plateau immediately.

**How to apply — session reports:**
- When enumerating recent activity, prefix each ship with its class: "v0.6.431 [skill/maintenance/bleed-stop/miss]".
- When answering "did we ship today?" the honest answer is "one maintenance ship" or "zero skill ships," not "one ship."
- When summarizing a week or month, report "N skill / M maintenance / P bleed-stop / Q miss" — not just N+M+P+Q.

**How to apply — the debug page:**
- Recent Activity section on `corrections_debug.html` should visually distinguish the four classes (color code, badge, whatever). Turning "ship count" into "skill-ship count" for the running total prevents the same illusion the audit surfaced.

**Related:**
- [[feedback_frame_exhaustion_watch]] — impact-class trend feeds exhaustion detection
- [[feedback_co_owner_posture]] — "recommend the full fix, not the middle-ground half" applies here too: report the honest classification, don't inflate the count
- [[feedback_dont_invent_numbers]] — impact class is claim-worthy; downgrade if numbers don't support it
