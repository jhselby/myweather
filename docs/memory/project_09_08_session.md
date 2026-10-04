---
name: project-09-08-session
description: "09-08 Tue morning digest session. 3 ships (v0.6.561→v0.6.563) + 1 collector deploy. Sentry plumbing (KILLED registry + τ-suspect L2-applied gate) + l4_nbm cc DROP pulled from 09-09. Two morning HOTs (ch.chp_nbm, h.l3_nbm) diagnosed as legacy pair-log from v0.6.551 kills; t τ-suspect diagnosed as selector-routing mislabel."
metadata: 
  node_type: memory
  type: project
  originSessionId: c60d99ab-2414-473e-8bfe-c2acd1f3e6b3
  modified: 2026-09-08T12:33:08.038Z
---

# 09-08 Tue — sentry plumbing + l4_nbm cc DROP

Digest 180/180 pass. 3 ships. 1 collector deploy.

## Ships

**v0.6.561** — `nbm_regression_sentry.py` KILLED_LAYERS registry `{(field, layer): kill_date_iso}`. When sustained-window start ≤ kill_date and cell has any rows, verdict is KILLED with a "pre-kill rows aging out" note instead of HOT/WATCH. Seeded with (ch, chp_nbm) and (h, l3_nbm), both 2026-09-05 (v0.6.551). Digest exec-summary greps HOT/WATCH → alerts stop firing automatically. Verdict flipped from "2 HOT" to "CLEAN — 6 nominal (7 THIN)". Analysis-only, no publisher deploy (sentry not in `publisher/main.py:PUBLISHERS`).

**v0.6.562** — `build_executive_summary.py:layer_shape_sentry` τ-suspect flag now requires L2 MAE to differ from L1 MAE by ≥1% at the long-hurt band before labeling as decay-τ. Same class of guard as v0.6.548 marginal-help + v0.6.558 flip-magnitude. Verified 0 τ-suspect lines emitted (was 1: t/production).

**v0.6.563 + collector deploy** — `l4_nbm.py`: `L4_NBM_FIELDS = ("ch",)`. cc dropped. Pulled from scheduled 09-09 slot ([[l4-nbm-cc-drop-prep]]). Deploy landed 12:14 UTC, first tick 12:17:02 clean.

## Two false-positive HOTs diagnosed as legacy

Both `ch.chp_nbm` (Δhelp +213pp) and `h.l3_nbm` (Δhelp +6pp) were flagged HOT on the fresh 3d window. Both trace to v0.6.551 kill on 09-05 15:18 EDT + v0.6.552 collector deploy 09-06 — fresh 3d window contained ~9-13h of pre-kill fires. Kills already live; sentry had no way to know. Absolute MAE actually dropped on both (chp_nbm 16.66→9.81; ch input was trivially easy at fresh MAE 2.64, any residual layer error inflated help% into extreme negatives). KILLED registry now suppresses. Natural clearance ~09-15 when both windows post-date the kill.

## t τ-suspect diagnosis

Morning top alert: `t/production τ-suspect: helps 0-5h -7.7%, hurts 12-23h +5.3%. Classic decay τ too long.` **Wrong label.** Per-lead breakdown from `time_series_diagnostic.json`:
- L2 (τ=4h) fully decayed by lead 6 — L2 MAE = L1 MAE from lead 6 onward.
- All HRRR-side layers (l2/l3/l4/l6/l1r) converged to l1 at lead 12+. Every delta 0.00.
- Only `nws` (NBM-derived) column materially different at 12-23h.
- Production tracks nws row-for-row: lead 15 nws-l1 +0.31, prod-l1 +0.15 → ~48% NBM-routing fraction.

Real driver: L1 selector routing to NBM at leads 12-27 where NBM raw is ~5-14% worse than HRRR. Known transient — L1 recency-override aftershock post-v0.6.540; by-regime walker armed 09-06 (v0.6.552) is the fix, earliest 7/7 clear 09-14. v0.6.562 added the sentry guard so the τ-suspect heuristic stops misdirecting on decayed-L2 shapes; the routing fix itself is passive.

**Why:** τ-suspect was checking "helps short, hurts long" without checking whether L2 is actually applied at the long band. Same class as sentry flip-magnitude fix (v0.6.558): symptoms-vs-mechanism gap in the alert. See [[feedback_check_own_arithmetic]] + verify-mechanism-not-shape discipline.

## Aside — Selector Skill tile color

User asked why 24h median 54.2% is orange while 7d 57.4% is green. Thresholds at `corrections_debug.html:4413` are `{win: 55, lose: 50}` for selector_skill — ≥55 green, 50-55 orange (flat), <50 red. 54.2 is 0.8pp shy of winning. Working as designed.

## Flags left open / followups queued

1. **KILLED_LAYERS pruning** — remove (ch, chp_nbm) and (h, l3_nbm) once both windows post-date kill (~09-15). Natural THIN afterward.
2. **h_hsf KILL** — digest says kill C1e axis. Real refactor: hsf is wired at `confidence_layer.py:464` as 5-tuple `spread_q::pt::trans::c1f::hsf_group` keys. Needs confidence-layer refactor + curator changes + walkforward gate. Dedicated session, not housekeeping.
3. **Deploy-hygiene enforcement** (carried from 09-07) — CLAUDE.md §8 addition or pre-push hook on `analysis/*.py` in PUBLISHERS.
4. **NBM-side specialist workstream** (carried from 09-07).
5. **Walkforward ADD t/wd/ws to l3_nbm** — hold. Sentry THIN (n=0-28) on those fields, and t is a historical kill (v0.6.472). Needs its own investigation before touching.

## Clock-watches

- 09-14 earliest by-regime walker wire (day 3/7 today).
- 09-15 KILLED_LAYERS registry prunable.

## Related

- [[l4-nbm-cc-drop-prep]] — the prep memo the DROP executed against.
- [[project_09_07_session]] — publisher CF stale + scoring audit + v0.6.558 flip-magnitude gate (the immediate predecessor for today's τ-suspect guard).
- [[feedback_baseline_is_user_default]] — informed the scoreboard framing.
