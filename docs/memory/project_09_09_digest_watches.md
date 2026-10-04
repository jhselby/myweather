---
name: project-09-09-digest-watches
description: "Two new digest watches opened 09-09 — L3_FIELDS DROP cm (streak 1/7, HRRR walkforward) + l3_nbm ADD wd proposal (wd.l3_nbm sentry cleared THIN → CLEAN, no longer suppressed)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f584257-df4f-41a9-b227-c4bdf632ea0a
  modified: 2026-09-09T11:31:15.298Z
---

# 09-09 Wed — two new digest watches

Digest was 180/180 clean; three HOT/WATCH sentries all logged false-positives. Two new items to track.

## Watch 1 — L3 DROP cm (HRRR walkforward)

- `walkforward_l3l4_validator` output: L3 ship `{wg, ch}`, current runtime L3_FIELDS `{ch, cm, wg}`.
- Divergence report: STREAK **1/7 (6 to go)** on drop-cm. First day proposed.
- Earliest ship window: 2026-09-15.
- Reference tile: `analysis/scoreboard_v2.py` per_field cm corr = +10.5% (7d, still positive) — cm is not clearly hurting production yet; walkforward sees the ship-side signal.

**Why:** first day of the 7-window streak. Held to gate discipline.
**How to apply:** on 09-15 digest, if streak = 7/7, action is `decay_apply.py` L3_FIELDS remove cm + collector deploy. Do not act sooner.

## Watch 2 — l3_nbm ADD wd proposal

- `nbm_walkforward_validator`: `ADD h,wd; DROP cc` on l3_nbm.
- **h addition blocked** by KILLED_LAYERS registry entry `(h, l3_nbm) = 2026-09-05`. Do not act; ADD would collide with recent explicit kill.
- **wd addition new signal:** wd.l3_nbm sentry was THIN in 09-08 morning memo, now CLEAN with n_sust 7,455 / n_fresh 3,285. Layer help delta +1.8pp, not degraded.
- Skip-table hints from walkforward: 5 wd cells hurt (se_flow/6-11 +4.9%, se_flow/12-23 +4.7%, ne_flow/12-23 +3.3%, sea_breeze/24-47 +15.9%, ne_flow/24-47 +3.8%) — would need SKIP_TABLE cells if wired.

**Why:** wd is a chronic wind-direction routing problem (per [[project_wd_l3_l4_circular]]); adding an L3_NBM cascade to it changes routing topology.
**How to apply:** if wd holds 7-window in walkforward AND sentry stays CLEAN, this becomes a promote candidate with SKIP_TABLE work needed. Not a housekeeping ship — dedicated session. If cc.l3_nbm HOT (currently investigating) turns out to need cc DROP, do that first; the ADD wd conversation is orthogonal.

## Related

- [[project_09_08_late_evening_session]] — yesterday's session summary + attribution decomposition ship
- [[project_09_08_evening_session]] — walker gate loosen (09-11 wire)
- [[project_cc_l3_nbm_watch_09_08]] — the standing cc.l3_nbm 24h REGRESS watch
- [[project_sr_l5_l3_nbm_sentry_false_positive_09_08]] — sr false-positive class
