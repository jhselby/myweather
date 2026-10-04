---
name: 09-14-session
description: "2026-09-14 Mon full-day session — 9 ships (v0.6.609-617). Marquee: 3 silent-tool-bug fixes (walker off-by-ones × 2, orthogonality-tool scope-limit × 1). Also: L3_NBM skip cell wd.se_flow/12-23h, sentry HOT investigation closed as 3-day noise, 12h short-window on scoreboard + per-field diagnostic (backlog item), tool audit sweep, 3 stale ENABLED=False comments cleaned. 3 investigations queued for next sessions."
metadata: 
  node_type: memory
  type: project
  originSessionId: c656ec98-2726-4d09-8e93-674722e5843d
  modified: 2026-09-14T15:27:37.949Z
---

# 2026-09-14 (Mon) session — 9 ships, 1 collector deploy

## Ships

- **v0.6.609** — L3_NBM skip cell `wd.se_flow/[12,24)`. Two-window CONFIRMED: 14d n=953 −4.60%, 50d n=2,581 −9.79% halves −14.24/−5.26. Collector rev `00568-wot` at 11:06 UTC. Only 1 of the 3 morning-CONFIRMED audit lines was net-new (wd/se_flow/6-11h was already shipped v0.6.500; wg/nw_flow/12-23h shipped yesterday v0.6.608).
- **v0.6.610** — Debug page sweep: today's Recent Activity entry + Wed 09-17/18 clock-watch (wg.l3_nbm sentry HOT self-clear vs frontal/24-47h CONFIRMED promote) + post-ship watch entry for v0.6.609.
- **v0.6.611** — `ADDED_LAYERS` registry prune: removed sr.l5_nbm + sr.l3_nbm (both added 09-04 v0.6.548). Both sentries CLEAN today; suppression was already no-op. Clock-watch cleared.
- **v0.6.612** — Debug page clock-watch narrative: HRRR-wire day 3/3 cleared 3 cells (cc/ne_flow/12-23, wd/se_flow/24-47, ws/sea_breeze/24-47) — walker JSON regen'd 10:57 UTC before this morning's 11:06 UTC deploy, so 2 net-new HRRR routings are live in production this tick.
- **v0.6.613 — ROOT CAUSE** — `analysis/_residual_persistence_walker.py:117` had `cutoff = now - GATE_WINDOW_DAYS`, producing an 8-day window for a 7-day gate; `n_seen == GATE_WINDOW_DAYS` never fired even for cells SHIP every day. **All three residual-persistence walkers had zero cells cleared since inception.** Fix: `now - (GATE_WINDOW_DAYS - 1)`. Post-fix: wg 16 cells cleared, h 7, dp 6. No runtime change (all three processors ENABLED=False).
- **v0.6.614 — SAME BUG** — post-v0.6.613 audit swept for the pattern. `analysis/h_chp_cell_gate.py:137` had the identical off-by-one. Post-fix: 11 cells cleared. 4 overlap `_CELL_SKIP`; 7 net-new dynamic suppressions (ne_flow all bands, nw_flow/6-11+24-47, pre_frontal/6-11, se_flow/12-23). Correlates with `h_chp_midlead_regression` ESCALATE on lead 11 — two tools converging on the same mid-lead regression.
- **v0.6.615** — 12h short-window (days=0.5) added to `scoreboard_v2.py` and `per_field_scoring.py`. New "Per-field diagnostic — 12 hour" debug-page table below the 24h one. 6h considered and dropped — pair-log has 8h backstamp lag so 6h is typically empty. 12h reliably has data. Sample: `ch` 24h Total Lift −10.8% flipped to 12h +11.1%; `ws` 12h −14.6% vs 24h −1.8% (fresh regression flagged).
- **v0.6.616** — C1d KILL scope-artifact fix: digest emitted "→ KILL C1d: signal captured by C1a/C1e (6/8 redundant)". Root cause: `h_cloud_disagreement_orthogonality.py:46` `MIN_N_PER_CELL=100` limited the tool to 24-47h cells only. At n=100 only 8 cells clear the floor — the tool KILLed C1d while being blind to 3 of the 5 live C1d SHIP cells (at 12-23h). Lowered to n=50; new verdict MIXED (3 orthogonal / 17 redundant / 8 other). Do NOT unwire C1d.
- **v0.6.617** — Post-audit sweep + stale-comment cleanup. Walker-cutoff and orthogonality-scope patterns audited across all matching scripts — no new bugs. 3 stale ENABLED=False comments corrected (marine_layer_correction, ws_bias_persistence, cl_persistence_gate) — cleared misleading flip-date promises weeks past with no clear signal date.

## Investigations that closed cleanly (no ship)

- **wg.l3_nbm sentry HOT** — 3-day dip against a durably-earning cell. 5-window per-regime × band dig identified `nw_flow/24-47h` as the un-skipped negative driver (fresh −14.02% n=307 but 50d +1.75% n=4,387 halves both positive — not skip-worthy). Real watch target is `frontal/24-47h` (14d −4.54%, 50d −1.26%, halves unstable) — queued for Wed 09-17/18 audit re-read. See [[project_wg_l3_nbm_sentry_09_14]].
- **C1d KILL** — turned out to be scope-artifact of tool's MIN_N floor, not a real KILL. See [[project_c1d_kill_scope_artifact_09_14]].

## Common shape across the 3 tool-bug ships

**Silent-tool-blindspot pattern.** A tool's internal threshold/filter silently limits its own scope, producing a misleading verdict:

- v0.6.613/614: `cutoff = now - N days` + `filter >= cutoff` gives N+1 dates, so `n_seen == N` never fires.
- v0.6.616: `MIN_N_PER_CELL=100` limits orthogonality test to the largest-sample band, blind to same-axis cells at other bands.

Both are "tool thinks it's testing the whole thing; user thinks so too; actually testing only part." Discipline update: `feedback_digest_triage_discipline` step 6 — for KILL verdicts on live axes, verify test scope covers all live SHIP cells before acting. Same class of trap warrants a general audit step.

## Session lessons

1. **When you find a tool bug, immediately grep for the pattern.** v0.6.614 landed within 30 min of v0.6.613 because I swept for the same shape. The second bug was findable in ≤5 min once we knew what to look for.
2. **"0 cells cleared" as normal-looking output.** Both fixed walkers had been reporting "0 cleared" for weeks and nobody investigated. Same class as v0.6.522's Stage 1 harness fix — mechanism silently mis-firing. Any "0" in a walker's cleared count deserves at least one "why 0" check.
3. **Test-scope vs live-target-scope mismatch is a KILL-verdict trap.** Applied to any redundancy/orthogonality tool.
4. **Comment cleanliness prevents state drift.** wg residual persistence was listed as "live via shared harness" in the stale project_todo.md for weeks while ENABLED=False — the memory promised what the code didn't deliver. Same class of miscommunication happens in inline ENABLED comments when they promise flip-dates that come and go without a state update.

## What surprised me

Post-v0.6.613 walker fix I expected 5-10 cells cleared. Got 16 wg + 7 h + 6 dp = 29 cleared. The gate had been broken since the shared harness landed (v0.6.532 08-31). That's ~2 weeks of "0 cells cleared" reports nobody flagged.

## What's queued (not started)

See [[project_09_14_queued_investigations]] — three items:
1. h/production τ-suspect (biggest live signal, needs τ vs SKIP decision)
2. cc/0-5h narrow-promote into C1d
3. ch/24-47h C1a-conditional recalibration

## Related

- [[project_09_13_session]] — prior day (7 ships + 2 debug sweeps).
- [[project_residual_walker_gate_off_by_one_09_14]] — deep dive on the walker off-by-ones.
- [[project_c1d_kill_scope_artifact_09_14]] — deep dive on the C1d KILL.
- [[project_tool_audit_09_14]] — the audit sweep after the 3 bug fixes.
- [[project_wg_l3_nbm_sentry_09_14]] — sentry HOT investigation.
- [[feedback_digest_triage_discipline]] — updated with step 6.
