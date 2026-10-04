---
name: project-09-09-evening-session
description: "2026-09-09 (Wed) evening 18:00-19:03 EDT. 1 ship v0.6.576: Difficulty column (raw_difficulty_ratio) wired into per-field diagnostic table between Total Lift and Pipeline Lift. Key read: t 0.98× h 0.95× yet still REGRESS → pipeline losses, not weather. 24h pipeline value-add +11.5pp against a HARDER HRRR raw baseline (real turn, not easy weather)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6643765b-86c4-46bd-9c0e-11977b0d53d0
  modified: 2026-09-09T23:09:55.599Z
---

# 09-09 Wed evening — Difficulty column ship

## What shipped

**v0.6.576** (commit d97ea48, pushed main, publisher CF revision 00023-dog deployed 22:51 UTC, first tick 23:02 UTC verified column live) — Difficulty column added to the per-field diagnostic table (`corrections_debug.html`) between Total Lift and Pipeline Lift.

- **Backend** (`analysis/per_field_scoring.py`): `_load_raw_difficulty()` reads `raw_difficulty_index.per_field[*].ratio` from local `analysis/output/mae_over_time.json` written earlier in the same publisher run (mae_over_time runs before per_field_scoring in `publisher/main.py:PUBLISHERS`). Injects `raw_difficulty_ratio` into every 7d per_field cell. 24h cells untouched (90d ref, no 24h analog). Silent skip if mae_over_time.json missing.
- **Frontend**: renders "1.XX×", bare ratio, no lift-color (direction-neutral per [[feedback_audit_label_direction_neutral]]). Bold when |ratio − 1| ≥ 0.15. Median + Mean foot rows added, unweighted-across-fields to match mae_over_time's own `mean_ratio`.
- **Convention doc** entry added.

## Ratio snapshot at ship (7d ÷ 90d ref)

- **Harder than usual:** cl 1.26×, pr 1.12×, wd 1.11×, cm 1.12× · Median 0.98× · Mean 0.95×
- **Easier than usual:** pa 0.56×, sr 0.77×, ch 0.86×
- **Near normal:** t 0.98×, h 0.95×, wg 0.98×, cc 1.01×

Key insight: **t and h still REGRESS with difficulty ratios near 1.0 → the losses are pipeline, not weather**. The 24h turnaround (pipeline +11.5pp vs HRRR, prod at 75.6% of HRRR MAE) came against a HARDER 24h HRRR raw baseline (t 24h HRRR 4.03 vs 7d 2.18 — nearly doubled), so pipeline is genuinely earning lift, not riding easy input.

## Scoreboard read (22:01Z snapshot before ship)

Pipeline value-add: **+5.9pp (7d) / +11.5pp (24h)** vs HRRR.

**7d:** STRONG ch (+53.9%), cm (+10.1%). GOOD ws/wg/wd/cc/sr. REGRESS **t −3.1%, h −8.7%, dp −4.6%** (all halves-agree, MED conf).

**24h:** t **flipped GOOD** (+9.95% vs NBM). STRONG ch (+66.6% HIGH), sr (+22.8% HIGH). Still REGRESS: **h −9.4%, cc −11.8% HIGH conf** (new — 7d is +4%), dp −2.1% (LOW, halves disagree). Largest cell hit: **h 6-11 band −59% n=120**. Selector high-conf cells dropped 35.7% → 14.3% window-over-window.

## Reference — pr row explanation (came up in session)

pr shows identical values in Total Lift / Pipeline Lift / HRRR Skill columns because it's HRRR-only (NBM doesn't publish pressure). For any HRRR-only field all three lift definitions collapse to `(hrrr_raw − prod)/hrrr_raw`. The −0.8% is L2 pressure gate (nw_flow 0-5 + 6-11 since 08-10) slightly under water on the 7d pool. Verdict WATCH, halves −0.48/−1.08. 14-day post-fix watch (started 08-13) worth a re-read soon.

## Live watches carried forward

- **cc 24h REGRESS HIGH conf** — revisit 09-11 per [[project_cc_l3_nbm_watch_09_08.md]]
- **h durable loser** — biggest single-cell drag (h 24-47 −21% n=3023 on 7d). No specific plan; NBM-side specialist workstream still queued.
- **t 24h→GOOD but 7d REGRESS** — not shipped-territory. Selector by-regime walker earliest wire 09-11-14.
- **sr.l5_nbm/sr.l3_nbm sentry HOT** — false positive from 09-04 sr add, ignore through 09-14 per [[project_sr_l5_l3_nbm_sentry_false_positive_09_08.md]]
- **KILLED_LAYERS registry** prunable ~09-15

## Related

- [[project_raw_difficulty_index]] — REFERENCE, v0.6.392 emit spec. Now surfaced on the scoreboard row not just the footnote.
- [[feedback_audit_label_direction_neutral]] — why the column has no lift-color and no "discount lift when >1" prescription.
- [[feedback_metric_provenance_labels]] — column header carries the formula "7d raw MAE ÷ 90d ref".
