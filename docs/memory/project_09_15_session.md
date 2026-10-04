---
name: project-09-15-session
description: "09-15 Tue session — 8 ships (v0.6.625–632). L3_FIELDS drop cm, digest streak fix, KILLED_LAYERS prune, audit filter, debug sweep, layout, Attribution+Total Lift reconcile, 12h open. dp/h fresh-fire diagnosed as v0.6.620 shadow (no action)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 826ae698-1457-47e2-a670-9f046fb5ffca
  modified: 2026-09-15T16:50:30.915Z
---

## Ships (8, all pushed to main)

- **v0.6.625** collector deploy (rev `myweather-collector-00574-guj`, 13:07 UTC) — (a) `L3_FIELDS = {"wg", "ch"}` in `decay_apply.py:78` — dropped cm after walkforward cleared 7-day gate on the drop proposal. (b) `build_executive_summary.py` streak walkback now requires matching normalized verdict text (strips `[entangled:N]`, `[N thin]` bracket clauses; keeps ship-count digits). Motivating case: walkforward L3L4 counter read "48/7 days confirmed" as bucket-continuity since 2026-06-25 through three intermediate ships (ws/cc L4/pp), but the "drop cm" proposal itself was only 7 days old.
- **v0.6.626** analysis + frontend — `nbm_regression_sentry.py` KILLED_LAYERS registry pruned `(ch, chp_nbm)` and `(h, l3_nbm)` (both 09-05 v0.6.551). `(cc, l4_nbm)` 09-08 and `(cc, l3_nbm)` 09-10 kept. Also removed two closed 09-15 clock-watches from debug page Upcoming.
- **v0.6.627** analysis — `nbm_skip_add_audit.py` now filters already-shipped cells via `_load_shipped_cells()` reading `skip_table_nbm_curated.json`. All 3 CONFIRMED cells in today's digest were already live (wd/se_flow/0-5h v0.6.622, wd/se_flow/12-23h v0.6.609, wg/nw_flow/12-23h v0.6.602) — walkforward re-emits proposals that cleared their 14d gate forever, audit re-surfaced them daily. Silent no-op if JSON missing.
- **v0.6.628** debug page sweep for 09-15 — Recent Activity 09-15 entry prepended, 09-14 downgraded, 09-13 trimmed to display:none. Upcoming grid added Thu 09-17 dp/h HEALING watch. 5 new Post-ship watches (v0.6.625×2, 626, 627, publisher redeploy).
- **v0.6.629** debug page — What's running section outer wrapper flipped from 3-column auto-fit grid to flex-column. Panels are dense text; narrow columns wasted vertical.
- **v0.6.630** analysis + frontend + publisher redeploy — **Attribution + Total Lift reconcile**. Backend `per_field_scoring.py` emits `routing_paired_pct` and `cascade_paired_pct` on the same paired pool + same 2dp rounding as `total_vs_best_raw_pct`. Frontend Attribution reads directly instead of recomputing from *_mae (which used 3dp intermediates → ~0.5pp drift vs Total Lift's 2dp headline). Now Routing + Cascade = Total per field, and Attribution Total = Total Lift by construction. Verified end-to-end 16:00 UTC GCS tick: t 7d = 7.40 + 0.72 = 8.12.
- **v0.6.631** debug page — 12h per-field diagnostic `<details>` default-open, matches 7d/24h above it.
- **v0.6.632** debug page — 09-15 Recent Activity entry filled in v0.6.629/630/631 + reconcile description.

## Non-ship work

- **Publisher CF redeployed twice.** First at 14:00:58 UTC to close the v0.6.615 12h WINDOWS lag (published 09-14, publisher last-deployed 09-13, GCS JSON only had 7d + 24h). Second at 14:46:15 UTC to pick up v0.6.630's routing_paired_pct/cascade_paired_pct fields. Both verified via freshly-published GCS JSON.
- **Digest triage:** dp + h "FRESH FIRE" (3d prod_real +30/+35% worse than raw) diagnosed as a **v0.6.620 frontal-detector threshold shadow**, not a live regression. prod-replay reconstructs cleanly under the new 4.0°F threshold; prod_real for 09-13 and early 09-14 was served under the old 8.0°F threshold's regime-stamp misses. dp is derived from (t, h) via Magnus so h regression drags dp along mechanically. Expected roll-off 09-16/17 as pre-fix pairs fall out of the 3d fresh window. No ship needed.

## Root causes worth remembering

- **"48/7 confirmed" is bucket-continuity, not proposal-continuity.** The digest streak counter walked back through `digest_history.jsonl` counting days the script was in "promote" bucket, without checking whether the specific proposal had stayed the same. Prior ships in the same bucket (ws → cc L4 → cm) reset the *proposal* but not the *bucket*, so the counter accumulated across ships. v0.6.625's streak fix normalizes verdict text before comparing.
- **prod_real vs prod-replay divergence isolates runtime/state-only regressions.** If replay reconstructs clean and prod_real is hot, the fitter's tables and shape are fine — suspicion goes to regime-stamp or state-plumbing changes made in the interval, not the corrections themselves. This shortcut worked twice today (h L2 retune cleared; frontal detector was the actual driver).
- **Publisher redeploy pairs with analysis edits** (`feedback_deploy_hygiene_publisher_pairs_analysis`). v0.6.615 shipped 12h WINDOWS to per_field_scoring.py + a changelog note claiming "GCS-published files now carry 12h" — but publisher CF was never redeployed. Two days of user-visible blank table before Joe noticed. Same pattern would have hit v0.6.630 (routing_paired/cascade_paired fields) if not deployed same day.
- **Attribution decomposition rounding trap.** Frontend recomputing `(b-s)/b` from separately-rounded MAEs propagates ~0.5pp of drift vs backend-emitted 2dp lift. Fix pattern: emit the aggregate at the same precision/pool as the headline, don't recompute.

## Clock-watches for 09-16 digest

- **dp + h HEALING check.** Sentry should flip HOT → HEALING or CLEAN as pre-v0.6.620 pairs (09-13, early 09-14) roll off the 3d fresh window. If 3d stays hot, dig for a second cause.
- **cc.l4_nbm KILLED_LAYERS prune candidate.** Kill date 2026-09-08 (v0.6.563). Sustained window on 09-16 = 09-09 to 09-16, one day past the kill date. Ready to prune if sustained_start > kill_date. `(cc, l3_nbm)` 09-10 kill still overlaps sustained_start — not ready until 09-18.
- **stagnant_high walker first read day 3/3.** v0.6.605 stamps landed 09-13; 3-day accumulation closes 09-16. Watch for cell candidates on ws/sr under stag (retroactive +16.6% / +35.4% lift). ch reverse-direction cells possible (HRRR-wire) given retroactive −46% anti-signal.
- **nbm_skip_add_audit CONFIRMED list should be empty or truly new.** v0.6.627 filter is live; any CONFIRMED cell surfacing should be a genuine new proposal, not a re-surface of shipped state.
- **Digest streak counter behavior.** Walkforward L3L4 should show 7/7 on the "L3 ship 2 [entangled: 0/1]" verdict — or drop out of ship-eligible entirely if the drop lands and verdict text changes to reflect. Any ship-resolution script's streak count resetting on a stable proposal would indicate the normalizer is too aggressive.
- **Attribution tile identity.** After the 16:00 UTC tick with v0.6.630 live, every field's Routing + Cascade = Total should hold exactly, and Attribution Total should match Total Lift headline exactly.

## Blocking / paused

- `frontal/24-47h` wg.l3_nbm still under ADD threshold — clock-watch 09-17/18 for CONFIRMED promote or self-clear.
- Publisher deploys landed clean; Attribution tile expected working on next hard-refresh.

Related: [[project_selector_recency_override_watch]] · [[project_simpson_guard_shadow]] · [[project_frontal_detector_health_09_14]] · [[feedback_deploy_hygiene_publisher_pairs_analysis]] · [[project_residual_walker_gate_off_by_one_09_14]].
