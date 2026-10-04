---
name: 07-21-session
description: "Tuesday 2026-07-21 marathon: 4 versions shipped (v0.6.371 real per-row Prod trajectory + digest FAIL fix + v0.6.371a Rule 5 sweep + v0.6.371b wd L2 fix), wdp ship pre-mortem doc landed, MEMORY.md compacted 20.4KB→10.6KB. Two new Stage 1 scaffolds (dp daily-residual persistence + pp Brier reliability decomposition). Two silent bugs surfaced: L1_ONLY_FIELDS classification lag masked wd L2 data → v0.6.371b fix; pp pair-log `forecast` carries L1 semantics → +6.7% Brier improvement been invisible for months (v0.6.372 fix booked). One new watch flagged: chp mid-lead 6-20h regression vs Lc (day 3/14 read; re-check 07-25)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0a14e1f9-f87a-464e-846e-dcdd5c525ad4
  modified: 2026-07-21T23:33:36.186Z
---

# 07-21 Tuesday session — 4 ships + 2 Stage 1 scaffolds + 2 silent bugs caught

Live version at EOD: **v0.6.371b**. Tue weekly-limit reset day per
[[project_tuesday_cadence]]; used the capacity.

## Ships (chronological)

- **v0.6.371 (AM)** — real per-row Prod trajectory in mae_over_time chart.
  Closes the honesty gap softened in v0.6.370a. `analysis/mae_over_time.py`
  adds `prod_real` accumulator (reads `error_{applied_layer}` per pair-log
  row, independent of STRICT completeness gate — parallels
  `decay_fit.py:712-729` for per-band tables). Frontend LAYER_STYLE gains
  `prod_real` (yellow #e0d472, width 2.0); FIELD_LAYERS swaps isProd from
  specialists (Lsr/Lc/chp/clp) + legacy `prod` key onto `prod_real` on
  all 13 non-wd fields. Specialists demote to intermediate lines (still
  visible as gate-fired-only MAE — useful for 14-day watches). **wd left
  alone** — no applied_layer stamps until wdp ships 07-27. Verified locally:
  ch prod=16.87, chp=16.98 (n=380 gate-fired), prod_real=14.87 (n=912).
  Sample-comparable to Raw/L2/L3.
- **l2_lead_decay_fit ZeroDivisionError guard** — digest FAIL at line 208
  (`mae_l1 == 0` on dry pp/pa windows). One-line `if r["mae_l1"] else 0.0`.
- **wdp ship pre-mortem** committed at `docs/preflight/wdp_ship_patches.md`
  as companion to the existing `wdp_preflight_checklist.md`. Every 7 sites
  written as exact `old_string` / `new_string` patches against live 07-21
  code (commit `7d7da66`). Both open decisions resolved (mae_over_time
  option (a); SHIP_EVENTS `<FLIP_DATE>` placeholder). 4 curl verification
  snippets + 5 known risk points. Goal: 07-27 is ~30 min copy-paste
  instead of ~2 hr under-pressure rewrite, given
  [[feedback_specialist_attribution_wiring]] has 3 catches for this
  exact pattern.
- **v0.6.371a** — debug page Rule 5 sweep. Rolled Recent activity to 07-21
  (07-20 demoted; 07-18/17/16/15 trimmed to CHANGELOG per rolling 3-day
  window). Advanced 14-day watch counters (Lc 5/14, chp 3/14, wd L2 2/14,
  ws L3 asymmetric 2/14). Updated "07-21 flip earliest" → 07-27 across
  ~10 sites (wg residual persistence 07-20 evening re-run 10/4/22 with
  Jaccard 0.45 vs 07-14 forced HOLD; wg L3 skip-table + ws L3 hardcode-
  replacement same 7-window gate). Added Mon 07-27 wdp Upcoming decision.
  Advanced C1h GATE CLEARED 12/7 days (Jaccard walker); C1d 1/7. Pipeline
  state header 07-20 → 07-21.
- **v0.6.371b** — wd L2 line missing on accuracy-over-time chart, L1_ONLY
  branch fix. See [[feedback_stale_field_classifications]] for the
  general lesson. `analysis/mae_over_time.py:51` had
  `L1_ONLY_FIELDS = {"wd"}` — correct pre-07-20, but v0.6.368a shipped
  wd L2 blend and v0.6.367 wired the joiner to emit `error_l2` for wd.
  My `compute_fresh_rollup` was still routing wd through the L1_ONLY
  branch that only reads top-level `error` — never touched `error_l2`.
  Data existed; accumulator ignored it. Compounded because `FIELD_LAYERS.wd`
  had l2 as isProd (v0.6.371 left wd alone since pre-wdp no applied_layer
  → no prod_real). Fix: extend L1_ONLY branch to also emit L2 for wd when
  `error_l2` is present. Verified: wd.l2 populates n=2 days (07-20+07-21).
  Frontend 3-day floor → L2 line appears starting 07-22 digest.

## New Stage 1 scaffolds (both landed today)

- **dp daily-residual persistence Stage 1** (`analysis/h_dp_residual_persistence_stage1.py`)
  — mirror of h/wg templates. First read: test +18.60% MAE on 26k rows
  (matches Stage 0 +19.06% from today's digest). Per-regime 4 WIN
  (sw_flow +27%, pre_frontal +23%, nw_flow +12%, frontal +9%) / 2 LOSE
  (calm −26%, se_flow −35%) — textbook regime-gate-able pattern. Halves
  sign-flip (training halves pre-HRRR-anomaly negative; test post-anomaly
  positive) — same fragility h + wg both showed at same stage. Verdict
  **MARGINAL**; regime-gated Stage 2 is the natural next shape. Re-run
  07-24. Auto-runs in daily digest from tomorrow.
- **pp Brier reliability decomposition** (`analysis/pp_brier_reliability.py`)
  — fills measurement gap flagged on debug page line 1347. Bins by
  predicted-probability decile, Murphy decomposition (Brier = Reliability
  + Uncertainty − Resolution), skill vs climatology. See
  [[project_pp_brier_reliability]] for the findings.

## Silent bugs surfaced (both real value)

1. **L1_ONLY_FIELDS stale classification** (v0.6.371b) — see
   [[feedback_stale_field_classifications]].
2. **pp "Production=L1 rendering bug" — RETRACTED same-day.** Initial
   finding from `pp_brier_reliability.py` showed L4 vs L1 +6.7% Brier
   gap and Production=L1 bit-exact — looked like a downstream rendering
   bug. Traced 07-21 PM to completion: pp was dropped from L3_FIELDS
   on 07-04 v0.6.304. Recent pair-log rows (07-12 → 07-21, 40k+ verified)
   have L1==L4 bit-exact — the "gap" was historical artifact from pre-drop
   rows still in the 30-day retention window. Fitter tsd correctly shows
   L1==L4==Production. **No bug; no v0.6.372 fix needed.** New lesson
   about pair-log window non-homogeneity added inline to
   [[feedback_measure_against_live_stack_baseline]].

## New watch flagged

- **chp mid-lead regression** (see [[project_chp_midlead_regression_watch]])
  — day 3 of 14 read from live tsd showed chp winning short-lead
  (leads 1-5) as designed BUT losing to Lc at mid-lead 6-20h (+14 → +53%
  over 15 leads, n=30-45/lead — not tiny sample noise). Suspected cause:
  Stage 2 SHIP-set was measured against L4, but chp ships AFTER Lc.
  Re-check day 7 (07-25); if persists at n≥100, escalate to SHIP-set
  re-verification against Lc-in-stack baseline.

## Housekeeping

- **MEMORY.md compacted** 20.4KB → 10.6KB (hook line ~600B → ~85B avg).
  Reorganized into 8 sections: active watches, settled, architecture,
  user, feedback (process/pipeline/code/infra/UI), session logs. Older
  session log entries dropped from index (files remain; lessons already
  extracted to standalone feedback/project memories).
- **Curated data sync** committed 20:00-ish: 19 files from AM digest re-runs
  (all Stage 2 curated tables + L5/Lc gate history caches).

## Ship calendar re-set at EOD

- **07-22 (Wed):** h daily-residual persistence Stage 1 re-run (digest auto).
- **07-24 (Fri):** dp Stage 1 re-run + sr Lsb Stage 2 halves + h_ws_octant
  re-read #2.
- **07-25 (Fri):** chp mid-lead regression day-7 re-check (explicit).
- **07-26 (Sun):** cl linear-ramp Stage 2 streak clears.
- **07-27 (Mon):** **triple ship** (wdp + ws hardcode-replacement + wg
  residual persistence) — largest single-day live-layer change since Lc
  if all clear.

## Feedback memories updated this session

- [[feedback_measure_against_live_stack_baseline]] — pp case added as
  the third catch (Lsr divergence, cc-sat kill, pp Production rendering).
- **NEW** [[feedback_stale_field_classifications]] — general lesson from
  v0.6.371b.

## Related project memories created / updated

- **NEW** [[project_chp_midlead_regression_watch]] — day-7 explicit
  re-check task 07-25.
- **NEW** [[project_pp_brier_reliability]] — findings + follow-ups.
- [[project_todo]] — refreshed at EOD with all above.
