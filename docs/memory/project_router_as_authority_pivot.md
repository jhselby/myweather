---
name: project-router-as-authority-pivot
description: "09-25 strategic reframe: L1 selector's per-obs override mechanisms (_IMS_SELECTOR_CELLS + _LEARNED_CELLS) are the routing authority. SHIPPED v0.7.5 (2026-09-26) as ch via ims-threshold + sr via GBM. Sr side landed as silent no-op (empty JSON + band-suffix schema bug); fixed 2026-09-29 v0.7.15. Both mechanisms now actually live."
metadata: 
  node_type: memory
  type: project
  originSessionId: db0e0f7d-96cd-471b-a038-fb5297164147
  modified: 2026-09-29T16:36:21.128Z
---

# Router-as-authority pivot — SHIPPED v0.7.5 (2026-09-26), sr side ACTUALLY LIVE v0.7.15 (2026-09-29)

## Ship

Commit `f053c88e` on main. Collector deploy landed 10:53:12 UTC, first tick 10:57:02 UTC clean (MEMPROBE 48.7→465.7 MiB, no NameError/KeyError/AttributeError). Both mechanisms nominally live in production:

- **ch** — `_IMS_SELECTOR_CELLS` populated with 10 cells from `analysis/l1_selector_ims_threshold_refit.py` (commit 3a11ca87). Halves-stable A/B lifts +37% to +76% on `error_prod_real`, ablation-cleared (commit f24ab785). `IMS_SELECTOR_SHADOW_ENABLED = True`. **Actually firing since 09-26.**
- **sr** — `weather_collector/data/l1_learned_selector_curated.json` populated with 5 sr STABLE GBM cells from v5 sweep (commit f9cc4443). `LEARNED_SELECTOR_SHADOW_ENABLED = True`. **DID NOT ACTUALLY FIRE UNTIL 09-29 v0.7.15** — see below.

Flag names preserved (`..._SHADOW_ENABLED`) for wire compatibility with telemetry consumers. Docstring already reflected that `True = live apply`.

## 2026-09-29 update — sr side was a silent no-op for 3 days

The v0.7.5 sr ship shipped the flag flip and the curated JSON, but **the sr side never actually fired** for 3 days. Two independent problems, both silent:

1. **Shipped `l1_learned_selector_curated.json` was empty** (0 cells). Somewhere between v5 candidate and v0.7.5 ship, the sr cells were dropped. The commit history isn't clear on when — probably an earlier ship attempt that "didn't visibly do anything," which was rolled back to empty rather than debugged.
2. **The v5 candidate JSON had a band schema mismatch.** Candidate used bands `"12-23h"` etc.; runtime `_band_for_lead()` returns `"12-23"` (no `h` suffix). Even if the candidate had been copied over verbatim, cells would have loaded silently and never keyed correctly at lookup time.

Fix (v0.7.15 commit `1a204c3e`, deployed 15:50 UTC 09-29):
- Re-ran `analysis/l1_selector_per_obs_classifier_stage1_v5.py` on current pair-log — same 5 sr STABLE cells held halves-stable including 4d nor'easter data
- Stripped `h` suffix from all band fields
- Copied to shipped path; backup at `l1_learned_selector_curated.json.pre-v0.7.15.bak`
- Deploy landed clean, first 3 ticks with zero `l1_learned_selector: gbm shape mismatch` warnings

The 09-28 dig noted "zero learned_gbm rows on sr" and correctly identified that the curated cells table was empty. That framing became "v0.7.5 verdict scope narrowed to ch-only" (see 09-28 session) — the observation was right, the interpretation as an intended scope narrowing missed the underlying bug. Corrected 09-29.

See [[feedback_shipped_flag_verify_effect]] for the general pattern of "flag flipped, effect didn't materialize."

## Why we shipped 6 days early

Prior plan blocked on ~10-02 fresh corpus (7d post-backstamp-fix). Two things made the wait redundant:

1. **The halves-stable A/B gate is the safety net that caught 09-24's blender stale-fit** (11 of 13 cells failed). The 09-25 refits used that same gate and returned tables where every cell passed A ≥3% AND B ≥3%. The corpus-freshness concern was already answered by the fit-time gate.
2. **v5 sweep ran 09-25, post backstamp appender live (09-24 v0.7.3).** The corpus the fits used already included fresh accumulated data.

Non-router cells fall through to the existing precedence chain (walker → band pool → HRRR), so shipped cells have no blast radius outside their fit window.

## Cells shipped

**ch (ims-threshold):**
```
('ch', 'ne_flow',     '0-5'  ): (73.5, 'H_low')     A+39.7%/B+39.3%
('ch', 'ne_flow',     '12-23'): (4.5,  'H_high')    A+58.3%/B+45.1%
('ch', 'nw_flow',     '24-47'): (43.5, 'H_low')     A+39.1%/B+65.8%
('ch', 'pre_frontal', '0-5'  ): (50.5, 'H_low')     A+61.1%/B+37.9%
('ch', 'pre_frontal', '6-11' ): (62.5, 'H_low')     A+63.7%/B+48.4%
('ch', 'pre_frontal', '12-23'): (78.5, 'H_low')     A+58.8%/B+56.4%
('ch', 'se_flow',     '6-11' ): (27.5, 'H_low')     A+58.4%/B+57.4%
('ch', 'se_flow',     '12-23'): (64.0, 'H_low')     A+69.1%/B+53.7%
('ch', 'se_flow',     '24-47'): (71.5, 'H_low')     A+75.9%/B+68.7%
('ch', 'sw_flow',     '12-23'): (84.5, 'H_low')     A+70.6%/B+58.3%
```

**sr (GBM cells, theta from v5 candidate):**
- sr/nw_flow/12-23h (theta 0.35)
- sr/nw_flow/24-47h (theta 0.70)
- sr/se_flow/12-23h (theta 0.45)
- sr/se_flow/24-47h (theta 0.45)
- sr/sw_flow/6-11h (theta 0.25)

## Rollback (one-liner)

Regression in either mechanism → flip the paired flag back to `False`. `_IMS_SELECTOR_CELLS` dict and curated JSON stay in place; the flag guard makes them inert. No revert-commit needed.

The prior ims-threshold table (v0.6.641, 09-20) is NOT preserved in code — pre-v0.7.5 curated JSON backed up at `weather_collector/data/l1_learned_selector_curated.json.pre-v0.7.5.bak`.

## Watch

- **First 7d pair-log (10-03):** ch and sr Value Captured tile columns should climb. ch was 7d VC +68% pre-ship; target >+70 (green threshold). sr was 7d VC +38%; target >+70 or the router isn't earning its keep.
- **24h tile is not the signal.** Small-n and regime-shift noise dominate. Wait for 7d.
- **First rollback trigger:** any of the shipped cells shows halves-stable failure on the fresh live pair-log at 7d.
- **Attribution now available (v0.7.7, 09-27):** `{f}_selector_mechanism` stamped alongside `{f}_selector_source` in pair-log. Values `ims_threshold` / `learned_gbm` mark router-driven picks. 10-03 verdict can compute per-cell VC on router-attributed subset only, cleanly separating v0.7.5 impact from precedence-chain coincidence. See [[project_09_27_session]].
- **Regression signal 09-27 24h:** sr -68%, wg -39%, t -17% vs raw_nbm on the fresh 24h window. If sr and wg stay negative on 24h through 09-29, treat as a v0.7.4/v0.7.5 audit trigger, not "watch it roll off." Only 1 day of v0.7.5 GBM routing in that 24h window — hard to attribute conclusively yet.

## Related

- [[project_09_25_session]] — pre-ship narrative.
- [[project_09_26_session]] — this ship.
- [[project_l1_per_obs_gbm_experiment]] — 09-24 v4 result that motivated v5.
- [[project_backstamp_stale_09_24]] — corpus freshness dependency.
- [[project_l1_selector_per_obs_axes]] — the earlier IMS_SELECTOR ship (09-19); superseded by refit.
