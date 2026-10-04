---
name: cc-l4-nbm-watch-08-28
description: "CLOSED CLEAN 2026-08-30 — cc.l4_nbm HOT sentry opened 08-28, closed day 3: sentry dropped back to day-1 level, 14d walkforward EARN held all 3 days, product lift got BETTER, no cell curated (skip-proposal targets rotated across 3 days = mixture, not stable regression)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8c047e09-3a34-4078-b6a2-c36aecb5ff73
  modified: 2026-08-30T10:12:21.093Z
---

**cc.l4_nbm HOT sentry — opened 2026-08-28**

Fact: cc.l4_nbm sustained MAE 14.23 → fresh 18.73 (+31.7%, n_sust 3,239 / n_fresh 2,534 — not thin). Digest sentry HOT. Scoreboard 7d cc verdict still GOOD (+6.6% vs best public, +15.2% vs HRRR) but `halves_agree = False`, confidence MED. Stage 4 also flags cc WATCH (ΔMAE −24.3%, bin shift 22.3pp).

Confirmed LIVE (not shadow):
- `L4_NBM_FIELDS = ("cc", "ch")` — cc in scope
- Selector table picks NBM for cc at all 4 bands (0-5, 6-11, 12-23, 24-47), lifts +12.9% to +20.5%
- Users see `cc_l4_nbm`

**Why:** Recent-window degradation showing up as sustained-vs-fresh gap + halves disagreement, but 7d aggregate still positive. Most likely a regime-mixture artifact (Stage 4 bin shift 22.3pp supports this), not an L4 hourly-residual drift — but can't rule out drift without another day of data.

**How to apply:** Next session's digest sweep — check if HOT persists AND whether 7d cc verdict has flipped from GOOD toward WATCH/REGRESS. If both, investigate L4_NBM hourly residual table freshness + weather-mixture correction. If HOT clears or 7d holds, close this watch. Related: [[project_cc_combine_walker]], [[feedback_mixture_check_window_semantics]].

**08-28 evening deep-dive (pair-log tail, ~4d, ~2,376 cc rows):**

- 14d walkforward: cc.l4_nbm vs l3_nbm baseline EARN +5.80% (per-band +4% to +7% help). Layer verdict is CLEAN.
- Recent 4d pair-log tail, pooled vs L3: 0-5h **+1.2% hurt**, 6-11h −3.0% help, 12-23h −3.7% help, 24-47h **+0.9% hurt**. Genuine mixture-shift — L4 has drifted toward wash/slight-hurt in some bands.
- Recent 4d vs NBM raw pooled: all 4 bands worse by 3-21% — this is the "prod losing to raw" symptom driving the scoreboard's Total-Lift regression on cc, but per [[dp is derived]]-style guidance and [[feedback_pooled_n_time_thin]], short-window comparisons don't override 14d walkforward.
- Interesting cells if regression persists tomorrow: **sw_flow 12-23h** (n=241, L4 hurts L3 by +6.9%), **sw_flow 24-47h** (n=556, +6.2%), **sw_flow 6-11h** (n=82, +14.1%). These would be the first curation targets in `skip_table_nbm_curated.json` under `l4_nbm.cc` if the walkforward flips.
- **Action today: none.** Watch it. If walkforward EARN verdict holds tomorrow, close the watch. If walkforward flips to LOSE and sw_flow cells replicate, curate.

**08-29 morning re-check (day 2):**
- Sentry WORSENED: sust→fresh +31.7% → +55.2%. n_fresh 2,169.
- 14d walkforward: EARN +5.4% (was +5.80%) — verdict HOLDS.
- 7d Total Lift vs NBM raw: +8.89% (was +6.6%) — got BETTER pooled.
- 24h Total Lift vs NBM raw: −3.54% — genuinely hurting in the last day.
- **Skip-proposal target FLIPPED:** yesterday's watchlist (sw_flow 12-23/24-47/6-11) is quiet today. Today's proposal is **se_flow 12-23h n=245 lift=−12.6%**. Cells rotating = mixture shift, not stable cell-level regression.
- Decision: don't close (recent-window damage real), don't curate (no cell replicated across two days). Extend watch one day. Close if sentry drops OR se_flow doesn't replicate 08-30. Curate se_flow 12-23h only if walkforward flips to LOSE AND cell replicates.

**08-30 morning re-check (day 3) — CLOSED CLEAN:**
- Sentry: +55.2% → **+32.7%** (back to day-1 level). Sust MAE 15.003 / fresh 19.904, n_fresh 2,295. Close rule (sentry drops OR se_flow doesn't replicate) satisfied on the sentry-drops branch.
- NBM walkforward divergence report: no l4_nbm entry (only l3_nbm ADD t,wd / l5_nbm DROP sr / l6_nbm DROP t / wdp_nbm DROP wd). l4_nbm cc EARN held all 3 days.
- Skip-proposals for l4_nbm cc today: **se_flow 12-23h n=347 lift=−31.3%** (replicated bigger) + new **sea_breeze 24-47h n=226 lift=−16.5%**. se_flow replication alone doesn't trigger curate — the AND condition (walkforward LOSE AND cell replicates) failed on the walkforward leg.
- **Verdict: CLOSE.** Consistent with new [[feedback_nbm_regression_sentry_semantics]]: HOT sentry alone ≠ regression when walkforward + product lift hold. Skip-cell target rotated across 3 days (sw_flow → se_flow → se_flow+sea_breeze) — mixture behavior, not stable cell-level regression. If se_flow 12-23h persists a 4th day AND walkforward flips, revisit — but not on this watch.
