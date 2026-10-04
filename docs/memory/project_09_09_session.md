---
name: project-09-09-session
description: "09-09 Wed session — 4 ships (v0.6.571-574). Built symmetric REMOVE-side curation loop on NBM skip table; shipped first-ever REMOVE curation (5 net cells removed); caught 2 premature removes via 50d cross-check and formalized two-window verdict. NBM cascade port state reframed: ports are architecturally complete; the missing discipline was symmetric skip curation, not more gates."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f584257-df4f-41a9-b227-c4bdf632ea0a
  modified: 2026-09-09T16:52:11.625Z
---

# 09-09 Wed — NBM skip-table symmetric curation loop

Started as digest triage + What's improving cleanup. Ended as 4 ships including a new mechanism for the NBM skip table.

## Ships

**v0.6.571** — debug page cleanup pass (Upcoming grid + Post-ship watches). Pruned 5 ✓-completed rows + 3 CLOSED-CLEAN items. L1 walker milestone rewritten to `~Fri 09-11` reflecting v0.6.566 gate loosen. Also backfilled `CHANGELOG.md` for v0.6.569 (attribution decomposition) + v0.6.570 (debug text sweep) which had shipped yesterday but weren't in the changelog.

**v0.6.572** — `analysis/nbm_skip_earning_audit.py`. Symmetric REMOVE mechanism on the NBM skip table. For every cell in `skip_table_nbm_curated.json`, evaluate on 14d of pair-log data: what would `error_l3_nbm` have been if this cell were not skipped, using the current pooled `l3_nbm_curated.json` bias. Compare MAE(counterfactual) vs MAE(input). If lift ≥ 3% with n ≥ 50 AND both halves positive → REMOVE candidate. Wired into `build_executive_summary.py` — new "NBM stale-skip proposals" section directly below the existing ADD-side proposals. Analysis-only, no runtime impact.

**v0.6.573** — First REMOVE curation. Audit flagged 7 of 19 cells as REMOVE. Shipped all 7. Table: 19 → 12 cells. Deployed to collector (revision 00555-hiz, 15:19 UTC).

**v0.6.574** — Two-window verdict + revert 2 premature removes. 50-day cross-check of v0.6.573's 7 ships surfaced 2 that failed the longer window: `h se_flow 24-47h` (50d lift −2.22%, halves −8.60/+8.38 — skip still earns) and `wg nw_flow 6-11h` (50d halves-unstable −4.55/+12.76). Both cleared 14d only. Reverted. Audit now requires BOTH 14d fresh AND 50d long windows to clear before emitting REMOVE — new WATCH verdict for 14d-only signals. Table: 12 → 14 cells (final).

## The 5 net removes (confirmed robust on 50d, still gone after revert)

All l3_nbm.wg, all halves-stable on both windows:
- wg se_flow 0-5h  (n=257, 50d lift +5.01%)
- wg se_flow 6-11h (n=357, 50d lift +5.92%)
- wg se_flow 12-23h (n=870, 50d lift +4.62%)
- wg nw_flow 12-23h (n=943, 50d lift +6.64%)
- wg pre_frontal 12-23h (n=449, 50d lift +7.76%)

These 5 now apply pooled L3 bias. Users see improved wg cascade contribution in NBM-routed rows for these regime × band cells starting 16:24 UTC.

## Reframe of the NBM specialist workstream question

Session started by discussing whether to build `wg_residual_nbm` (clone HRRR gate to NBM). Two rounds of reframing:

**Round 1 (my error):** Claimed NBM specialists were mostly missing. **Wrong.** The parallel cascade was fully ported 08-19 → 08-26 (v0.6.437 → v0.6.499). Fully mature layer-for-layer: L2 native, L3, L4, L5, L6 (scaffolded), chp_nbm, wdp_nbm. Real pattern isn't "no specialists" — it's "we ported 10, 6 failed to earn (killed/dropped)."

**Round 2 (my error):** Claimed L3_NBM was regime-blind (pooled only). **Also wrong.** L3_NBM is pooled bias PLUS a skip_table with 19 (regime × band) cells that suppress the pooled correction where evidence shows it hurts. The skip table IS the regime layer. Compare HRRR L3 = per-(regime, band, fc-quartile) bias + skip; NBM L3 = pooled bias + regime skip. Different mechanism, same intent.

**Real finding:** NBM's ADD-side skip curation runs daily (walkforward validator), but nothing was symmetric on the REMOVE side. 12 days of ADD proposals accumulated since 08-28 unshipped. Zero REMOVE proposals had ever been generated. That asymmetry is the real "why aren't NBM specialists earning" — not that specialists are missing, but that the curation loop was half-running.

Also caught: **I got L3_NBM diagnostic wrong twice today.** My first diagnostic (`l3_nbm_fit_by_regime.py`) reported L3_NBM ch/sr as net-negative (pool_v_raw −49% and −16%). The finding was a protocol artifact: my strict train/test split used 7-14 day stale training data, but production refits daily. Actual stamped `error_l3_nbm` shows L3_NBM helping +19% on ch, +16% on sr in production. See [[feedback_measure_before_concluding]] class — the sentry was right, my diagnostic was wrong. Corrected mid-session before recommending kills.

## Digest wiring (permanent)

- `nbm_skip_earning_audit.py` auto-picks up in daily digest (`run_digest.sh` iterates `analysis/*.py`).
- `build_executive_summary.py`:
  - `NBM skip-table proposals (...)` — ADD-side (unchanged, existed since v0.6.462).
  - `NBM stale-skip proposals (...)` — REMOVE-side (new v0.6.572, refined v0.6.574).
  - `NBM stale-skip WATCH (...)` — 14d-only signals not confirmed by 50d (v0.6.574).

Full symmetric curation loop now runs unattended.

## Post-v0.6.574 skip audit state

14 cells (l3_nbm: wg 10, ch 2, h 2). Verdicts today: 0 REMOVE, 3 WATCH, 10 HOLD, 1 THIN.
- WATCH: `wg sea_breeze 6-11h`, `wg nw_flow 6-11h`, `h se_flow 24-47h`.
- The 2 latter are the reverts — 14d says earn-back, 50d says no. Correct behavior.

## Two new memories to reference

- [[project_09_09_digest_watches]] — L3 DROP cm streak (1/7) + l3_nbm ADD wd walkforward proposal (still needs 7-window streak).
- [[project_wg_residual_nbm_scope]] — deprecated by this session's reframe. Kept for the architectural notes on how NBM cascade writes into forecast_snapshot's entry dict (relevant for any future NBM-side specialist scoped inline).
- [[project_nbm_specialist_diagnostic_scope]] — deprecated by the "skip curation is the answer" reframe. The A/B hypothesis question it posed is moot given the ports-are-fine, curation-is-asymmetric finding.

## Recommended session-start prompt for next session

> "Continuing 09-09 work. Symmetric REMOVE loop shipped v0.6.572-574 (5 net skip cells removed after 50d cross-check). Now: 12 days of ADD-side walkforward proposals accumulated since 08-28 — same rescore protocol applies. Consider running today's digest ADD proposals through rescore for curation. Also: 09-11 is the walker cell-wire read (day 3 of 3-day gate). Attribution decomp + selector routing correction is the priority event to watch. dp derivation override is the fallback ship if dp still REGRESS after 09-11."

## Lessons captured

- **Symmetry check.** Whenever we add a curation mechanism (ADD proposals), verify a REMOVE mirror exists. If it doesn't, the curated set drifts one direction over time. Same pattern applies to KILLED_LAYERS registry (has ADD, needs periodic prune audit — deferred).
- **Two-window verdict is the right shape for time-window-sensitive gates.** 14d catches freshness, 50d catches robustness. Neither alone is enough. This pattern applies to more than skip audits — any gate that fits on recent data should have a cross-check on longer data before ship. See [[feedback_streak_walker_robustness]] class.
- **Reading the codebase before making architectural claims.** I mis-framed NBM specialist state twice today. Direct fix: run `ls analysis/*nbm* weather_collector/processors/*` and read a couple of the actual files before saying "NBM has no X." See [[feedback_verify_writers_for_read_paths]].
- **The digest's ADD-side proposals are actionable evidence, not permanent alerts.** 30+ proposals accumulated 12 days unshipped because there was no cadence for curating them. The REMOVE loop we shipped exposed the same problem in the opposite direction; running the ADD-side backlog through rescore is the next natural workstream.
- **Diagnostic protocol matters more than I gave it credit for today.** My first L3_NBM regime-vs-pooled diagnostic used stale training data and reported the pooled L3 as net-harmful. Sentry (using stamped runtime errors, not re-fitted counterfactuals) was right. Rule for future: when re-fitting a diagnostic to compare against production behavior, mirror production's fit protocol (daily rolling refit), not a static one-shot fit.
