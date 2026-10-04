---
name: 07-25-session
description: "Sat 2026-07-25 session — 4 ships, digest triage, dprp Stage 3 wire, badge taxonomy, verbosity sweep, cluster_spread KILL verified as noise, wdp preflight drift-verified."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6eaa9453-6bb5-43c6-a502-11181da39f47
  modified: 2026-07-26T10:39:07.863Z
---

# 07-25 (Sat) session summary — 4 ships, 2 discretionary reads

## Ships (in order)

1. **`8d91ee0` — analysis: gate_firing_rollup allowlist.** Digest morning UNEXPECTED bucket flagged 4 dormancy items; all were designed dormancy the allowlist just didn't cover. Added `ch_persistence_gate/ch/frontal` (by-design skip per processor line 82: frontal is the one regime L4 wins), `cl_persistence_short_lead` (retired 07-24 v0.6.379, aging out by 07-31), `wg_residual_persistence` (ENABLED=False through 07-27). Bucket 4 → 1. Only `C1h/ch/sea_breeze` remained alerting — incidental co-firing with C1e "post" this week (6 frontal events in window, including 1 sea_breeze passage 07-19), not permanent design skip. Left alerting so a genuine dormancy later isn't masked.

2. **`86a124e` — v0.6.380 dp residual persistence Stage 3 wire (ENABLED=False).** Cloned from `wg_residual_persistence` template. New `weather_collector/processors/dp_residual_persistence.py`. Reads `hourly.corrected_dew_point_post_l2` stashed by decay_apply, adds fitted per-clock-hour L2-residual mean, replaces post-L3 dp in SHIP/MARGIN cells. Stage 2 preview (2026-07-22 v0.6.372d): 8 SHIP / 2 MARGIN / 26 SKIP / 1 THIN of 37. SHIP cluster cleanly long-lead (frontal 12-47h, nw_flow 24-47h, pre_frontal 12-47h, sw_flow 6-47h). Sanity clamp `|Δ| > 10°F` (Stage 2 fit range |≤3.15|°F). Preserve-before-mutate pre-key `corrected_dew_point_post_l3_pre_dprp`. First-tick verify post-deploy (calm regime, no SHIP cells): 47/47 correct skips. `KNOWN_LIVE_PIPELINES` + `EXPECTED_DORMANT_OPERATORS` entries added same-commit per v0.6.378 rule. Day 1/7 through 2026-08-01. Bundled daily fitter refresh (15 curated JSONs + 2 cache files) per v0.6.377b/v0.6.378 precedent.

3. **`18da7ef` — v0.6.380a Recent-activity category badges + RIGHT NOW dp row.** Recent activity was mixing 4 work types under one green `SHIP` badge. Split into 5-category taxonomy: **`PIPELINE`** (`#4ad29a` — correction stack changes), **`DISCOVERY`** (`#e0a070` coral — new signals/measurements/verdicts), **`INFRA`** (`#7090a0` cool grey — tooling/backstops/registries), **`DASHBOARD`** (`#a89ce0` purple — retained), **`PREFLIGHT`** (`#8fa5c4` blue — retained). Legend at top of Recent activity block. Backfilled 9 SHIP-labeled items 07-21 → 07-23 to correct category (5 INFRA, 3 DISCOVERY, 1 DASHBOARD). Broke out 07-24 into 6 badged items + 07-25 into 3. Scope: Recent activity only; Engineering updates section left with existing `SHIP` badges. Also: RIGHT NOW pipeline table skipped dp since inception — added Dew point (dp) row between Humidity and Wind speed. Reads `hourly.dew_point` (raw) and `hourly.corrected_dew_point`; delta auto-computes via `_fmtDelta`. Verified live: raw 51.9°F → corrected 56.2°F → +4.3°F.

4. **`888a1e1` — v0.6.380b Recent activity verbosity sweep.** Tightened all 17 badged narrative bodies 07-21 → 07-25. Target ~40% cut; actual range 20-50% depending on item length. Cut instrumentation framing ("Morning digest flagged…", "post-deploy…"), restated cell counts already visible in cards below, pre-key + commit-hash trivia, trailing feedback links where redundant. Every fact preserved: versions, dates, cell counts, verdicts, delta percentages, file paths, `[[memory-links]]`. Scope: badged item bodies only; day-summary lines, still-open watches list, legend, and Section D layer cards untouched.

## Ops incident: 07-25 15:01Z Pages deploy timeout

`888a1e1` GH Pages build succeeded, but "Deploy to GitHub Pages" step hung 10 minutes (15:01:53 → 15:11:58 UTC) then timed out. Transient GH Pages infrastructure hang, not our issue (v0.6.380 + v0.6.380a both deployed cleanly ~12 min earlier).

**Fix:** empty commit `7724dd9 "retrigger pages deploy for v0.6.380b"` — landed cleanly, wymancove.com serving v0.6.380b by ~18:41Z.

**Lesson:** If wymancove.com serves stale version >5 min post-push, check `curl https://api.github.com/repos/jhselby/myweather/actions/runs?per_page=2` first. Empty commit is the fix.

## Discretionary reads (end of day)

**Read 1 — cluster_spread KILL verification.** Morning digest said KILL (ORTHO 1 / REDUND 4 / THIN 15). Re-ran fresh ~12h later: STABLE (ORTHO 3 / REDUND 2 / THIN 15). Two non-THIN cells flipped verdict on marginal r-values (~1.0 threshold). See [[project_cluster_spread_noisy_verdict]]. **Don't act on the KILL** — axis_2 stays live.

**Read 2 — wdp preflight drift verification.** `docs/preflight/wdp_ship_patches.md` still 95% valid. One material update applied: SITE 1 insertion point 568 → 582 (v0.6.380 dp block landed between wg and applicability map). All 6 other sites: line drift only, text-anchors still grep-unique. See [[project_wd_persistence_gate]]. 07-27 plan intact: 5 min re-verify + 30 min copy-paste.

## Feedback captured

- **Badges as visible signal:** Joe noticed Recent activity had 4 distinct work types mixed under one badge. Take the taxonomy seriously — DISCOVERY vs INFRA vs PIPELINE vs DASHBOARD each answer a different question ("we learned…" vs "we fixed tooling…" vs "we shipped a correction…" vs "we updated UI…"). If a badged item does more than one, categorize by primary deliverable.
- **RIGHT NOW dp gap surfaced organically** because dprp just shipped and dp was suddenly relevant. Whenever a new field enters the correction stack, sweep the top-level dashboards for that field's presence (RIGHT NOW table, accuracy chart, pipeline table, applicability map).
- **Verbosity budgets differ by section:** Recent activity items can be tight (chronological context frames them); Section D layer cards need full context (people click in cold). Don't apply a page-wide sweep — target the section-appropriate zone.
- **Never claim to have done something without verifying** (Pages deploy incident): initial "pushed, done" was wrong — should have polled wymancove.com or GH Actions status before saying deployed. Joe's "I'm only seeing .380a" caught it after hours.
- **"3 minutes to check the last build" (Joe):** when a deploy claim gets challenged, the fastest disproof is `curl` against the GH Actions API. Don't launch investigation; grab the last 2 runs and read status.

## What's next

- **2026-07-27** flip cluster (day-4 of 3-day countdown as of 07-25): wg residual persistence, wg L3 skip-table extension, ws L3 hardcode-REPLACEMENT, wdp. Largest single-day flip since Lc.
- **2026-07-31** Lc post-ship watch closes; C1 Stage 4 re-audit outcome expected (was HOLD 07-25).
- **2026-08-01** dprp flip decision (day 1/7 started 07-25).
- **ws under-bias work** (asymmetric −29.2% under, 42.5pp gap) deferred to post-07-27 L3 drop for clean baseline; explicit Joe direction.
