---
name: project-sr-lsb-flip-gate
description: "Lsb (sr sea_breeze cc-gated Lsr override) FLIPPED ENABLED=True 2026-08-05 v0.6.394. Fresh 7-day gate on cc<25 narrow shape cleared 7/7 daily PROMOTE reads (07-30 → 08-05). Post-ship 14-day watch CLOSED CLEAN 2026-08-19: sr prod_real 84.16 vs raw 95.03 = +11.4% lift on n=15,985 pooled 14d."
metadata: 
  node_type: memory
  type: project
  originSessionId: b47c582e-3034-4250-bdf6-3f9a8b121792
  modified: 2026-08-19T09:26:26.998Z
---

## Status: LIVE, 14-day watch CLOSED CLEAN 2026-08-19

**Close verdict (2026-08-19):** pooled 14d sr prod_real MAE = 84.16 vs raw = 95.03 = **+11.4% lift** on n=15,985. Well above any noise threshold. No sign of the Day 1 pattern recurring. Removed from `OPEN_WATCHES` in `corrections_debug.html`. Watch closed clean; Lsb continues LIVE with no follow-up work.

## Status: LIVE, Day 1 red-flag Day 2 recovered

**Flipped 2026-08-05 v0.6.394** via `ENABLED = True` in `sr_sea_breeze_lsr_override.py`. Post-deploy verified: `applied: True` in 12:27 UTC tick.

**Day 1 (08-06):** prod_real 86.14 vs raw 66.73 = **−29% hurt**. L5-applied daylight hours 09–14 carried prod_bias +160 to +320 W/m². Held on action (see [[feedback_debug_page_canon]] discipline).

**Day 2 (08-07):** prod_real 66.29 vs raw 78.34 = **+15% help**, bias −25 W/m². Recovered. Watch continues normally through 08-19; 08-06 attributed to weather turning after correction over-committed on prior-window signal (same class of failure that hit ch on 08-07 — see [[project_ch_chp_regression_watch_08_07]]).

## Ship gate summary (07-30 → 08-05)

- 7/7 daily PROMOTE verdicts from `sr_sea_breeze_lsr_refit_stage2.py`
- Final Stage 2 (n_test=1,838): pooled Δ +11.34%
- Halves: A +23.9% / B +4.0% (both ≥ 0)
- cc-bin 0-25: +44.6% (n=718, halves +49%/+34%) — the narrow shape works
- Per-lead-band: all 4 SHIP
- Per-hour: 5 SHIP (12, 14, 17, 18, 19), 3 SKIP (13, 15, 16)

## Watch points for 14-day post-ship gate (through 2026-08-19)

- **Hour 13** is SKIP on test (base 148 → inter 181, −22%) but its +16.49 W/m² bias is still applied because the curator writes all hours. If sr Last-24h drags, add a per-hour SHIP filter to `sr_sea_breeze_lsr_refit_stage2.py` before rewriting curated JSON.
- **Halves B +4%** is much weaker than halves A +23.9%. If B stays weak through re-cuts, revisit narrowing further.

## Files

- `weather_collector/processors/sr_sea_breeze_lsr_override.py` — ENABLED constant + runtime override
- `weather_collector/data/sr_sea_breeze_lsr_curated.json` — hourly bias table + cc gate
- `analysis/sr_sea_breeze_lsr_refit_stage2.py` — Stage 2 refit (feeds curated)

## Do NOT confuse with

[[project_sr_unit_mismatch]] — separate analysis-script consistency issue. Now unblocked (Lsb is resolved); may reopen for that thread.

## Related

- [[project_07_28_post_reboot]] — captures the 08-04 flip cluster (dpbp shipped, wsbp still HELD on calm regime n=0)
- [[preflight_dpbp]] / [[preflight_wsbp]] — same-shape preflights
