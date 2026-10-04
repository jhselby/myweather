---
name: project-10-03-session
description: "10-03 session. 1 ship: v0.7.23 second L1-blender apply-flip (h/sw_flow/24-47). DEPLOYED rev 00608-jot but NOT COMMITTED — HEAD still v0.7.22. h escalated to SUSTAINED FIRE, diagnosed as an NBM source break, not a stack regression. v0.7.5 ch verdict slipped."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-03T12:00:00.000Z
---

# 10-03 session

## ⚠ State at session end — v0.7.23 DEPLOYED BUT UNCOMMITTED

**The collector is running code that is not in git.** Verified 10-04: live revision is still
`myweather-collector-00608-jot`, HEAD is still `020cda9a` (v0.7.22), and these three files are
modified in the working tree:

- `weather_collector/processors/l1_static_blend.py` — the APPLIED_CELLS change
- `index.html` — v0.7.22 → v0.7.23
- `docs/CHANGELOG.md` — v0.7.23 entry

**First action next session: commit these.** Plain `git push`. Ship commits in this repo carry
code + version + changelog only — leave the daily digest churn unstaged, matching the v0.7.19 /
v0.7.21 five-and-seven-file shapes.

## v0.7.23 — second blender apply-flip

`h/sw_flow/24-47` added alongside `h/nw_flow/24-47`. Two applied cells; the other 18 curated cells
keep stamping shadow telemetry.

```
APPLIED_CELLS = {"h": frozenset({("nw_flow", "24-47"), ("sw_flow", "24-47")})}
```

Chosen because it was the **only unflipped cell clearing the declared `min_n_rows: 400` gate**
(`l1_static_blend_curated.json:5`): n=830, lift vs served +39.0%, halves **41.8 / 35.7** — a 6.1pt
spread, tighter than the first flip's 38.7 / 33.9.

**Held deliberately, and the reasoning matters more than the choice:**

| cell | n | halves | why not |
|---|---|---|---|
| h/sw_flow/12-23 | 380 | 50.6 / 40.9 | 20 rows short of the gate — should cross within a day or two |
| h/nw_flow/12-23 | 210 | 27.2 / 31.4 | half the gate, despite the tightest halves spread on the board |
| h/sw_flow/6-11 | 173 | 68.3 / 38.2 | thin, 30pt spread |

`nw_flow/12-23` was the tempting one: tightest spread, sits on the band where h was bleeding, and
it was the only candidate that would have fired that day (live regime was nw_flow; sw_flow was
inert). **Not taken.** Taking it would have meant relaxing a declared gate from 400 to 210 the
morning after a bad sentry reading — moving the bar because of the fire rather than the evidence.
That is the exact shape of [[feedback_capitulating_to_pushback]] applied to a gate instead of a
person. The gate exists for days like that one.

**No verifier work needed.** v0.7.21's `counterfactual_served_err()` and the
`{f}_preempted_source_shadow` stamp are global to both blend paths, so a newly applied cell is
scored correctly from its first applied row. Checked, not assumed —
[[feedback_apply_flip_invalidates_shadow_verifier]].

**Deploy:** revision `00608-jot`, rollout instance 11:28:26 UTC, first tick 11:37:02 clean.
MEMPROBE 48.2 → 456.0 MiB (+407.8, 98.8s) — matches the clean pattern (09-26: 48.7→465.7,
10-02: 48.4→525.8). No NameError/KeyError/AttributeError in 200 log lines. Outgoing instance had
reached 939.6 MiB; by 10-04 the new one is at ~1006 MiB. Known leak per
[[project_collector_memory_leak_hunt]], reset by each deploy.

Gate behaviour verified directly before deploy:
`('h','nw_flow','24-47')→True · ('h','sw_flow','24-47')→True · ('h','sw_flow','12-23')→False ·
('h','nw_flow','12-23')→False · ('dp','nw_flow','24-47')→False · n_applied_cells=2`

## h SUSTAINED FIRE — diagnosed as an upstream source break, not a stack regression

Sentry escalated h from FRESH FIRE (10-02) to **SUSTAINED FIRE**: 7d +16.5% (n=7,106),
3d +30.9% (n=2,584). The layer-shape sentry's τ-suspect line (6-11h +19.9%, 12-23h +32.1%) is the
**same event seen from a second angle**, not an independent decay-constant problem.

Cause: ~90% of h rows carry `applied_layer = l2_nbm`, and NBM humidity broke at mid leads from
09-30. Per-band `prod_real` vs HRRR L1 (`error_l1`):

| day | 6-11h | 12-23h | 24-47h |
|---|---|---|---|
| 09-30 | 5.20 / 2.94 | 5.11 / 2.57 | 5.94 / 5.51 |
| 10-01 | 5.40 / 4.05 | **6.73 / 2.42** | 7.44 / 5.46 |
| 10-02 | 3.44 / 2.47 | 3.74 / 2.62 | 5.38 / 4.48 |
| 10-03 | 3.68 / 3.65 | 4.06 / 3.80 | 4.87 / 5.81 |

`raw_nbm` is itself the bad number (10-01 12-23h: 6.13 vs HRRR 2.42), so the selector is faithfully
routing to a source that broke. **Already receding** — 10-01 was the peak, by 10-03 the 12-23h gap
was 0.26 and 24-47h had flipped to prod_real better than raw. The 3d window still read hot because
it was dragging 10-01 along. No fix shipped for it, correctly.

Note the pair log uses `lead_h`, not `lead_hours` — a wrong key silently returns zero rows and an
empty result looks like evidence. Same trap as the 10-02 regime-key mistake.

## v0.7.6 shadow retro — scheduled 10-03 re-run, done

**9 SHIP-READY / 11 HOLD / 0 KILL / 0 THIN** (from 9/10/1/0 on 10-02). `dp/pre_frontal/12-23`
cleared its KILL; **no KILLs remain** on any curated cell.

`h/nw_flow/24-47` (the v0.7.20 cell) held SHIP-READY at +25.9%, n 436 → 584, halves 33.4 / 23.2,
with `n_applied_rows_7d: 0` and `n_excluded_no_counterfactual_7d: 0`. The measurement-trap fix is
clean and the debug page's predicted `n_excluded > 0` did not materialise — correct, because the
applied rows had not closed yet (see below).

## Carried, NOT done

- **v0.7.5 ch verdict — the 10-03 KEY DATE, slipped.** Needs per-mechanism live attribution:
  filter the pair log on `selector_mechanism == ims_threshold`, attribute the 10 live ch cells
  against their counterfactual. The morning fitter re-emitted all 10 cells halves-stable
  (+39% to +76%), but that is the fitter agreeing with itself, not the live value read.
  Rollback is one flag flip.
- **v0.7.20/21 live verify — still unobserved.** The `h_preempted_source_shadow` stamp (expect
  `nbm`) and the `hourly.corrected_humidity` writeback. **I got the timing wrong twice and
  corrected it:** the 10-02 applied rows came off the 08:57 EDT tick at leads 24–29 and 43–45, so
  they close 09:00–14:00 EDT on 10-03 and 04:00–06:00 on 10-04 — not "around 09:00" as I first
  said when local time was 07:47. Needs a pair-log refresh; by 10-04 they should all have closed.
- **Blender applicability-map registration — confirmed still missing.** Re-checked rather than
  trusting the 10-02 note: `describe_applicability` is imported nowhere, `collector.py:743` builds
  `weather_data["applicability_map"]` without it, the descriptor is still dead code. Matters more
  now — two applied cells, and the live map still shows 20 layers with no blender entry.
- **NBM skip-ADD pass — 4 CONFIRMED, not shipped.** `wd/nor_easter/12-23` (−24.6% both windows),
  `wd/se_flow/24-47` (−5.8% at 50d, n=6,071), `wd/nor_easter/24-47` (−17.9%),
  `wg/nor_easter/12-23` (−10.7%). **Drop the last from the batch** — halves −0.00 / −10.90, half A
  degenerate.
- **No REMOVE.** `wg/nw_flow/6-11` fails halves for the **third straight day**: 50d second half
  +2.80% against a +3.00% bar. Climbing (2.11 → 2.04 → 2.80), so it will likely clear soon. Hold.

## Pre-existing test failures found (not mine, not fixed)

`tests/test_layer_tuple_sanity.py` — `test_layer_tuples_match` and
`test_specialist_enabled_guards_present` both fail. Message is specific:

> specialist 'l1r' has no ENABLED guard in `forecast_snapshot._derive_applied_layer`.
> Add: `if lk == "l1r" and not <module>.ENABLED: continue`

**Bisected** across `c79c68dc`, `bed134b5` and `7e784cfb` — fails identically at all three, so it
predates the v0.7.20/21 ships. Something real is unguarded. Separate item, untriaged.

## Digest, other

- `pp` ANOMALY **improving** on its own: +177.7% → +125.0%. No action.
- `pa` WATCH **worsening**: +556.2% → +598.7%, still with no memory explaining it. The one
  genuinely untriaged sentry.
- New Stage-0 verdict flips, **backlog not ships** (aggregate-only, need the regime×lead cross-cut
  per [[feedback_regime_lead_band_cross_cut]]): `l2_lead_decay_fit` → IMPLEMENT (pr +4.2%, τ=8h),
  `h_diurnal_l2_tau_stage0` → PROMOTE. Also `h_pre_front_orthogonality` → KILL (pre-frontal is C1a
  re-skinned, no new axis).

## Corrects a stale memory

The carried item *"`corrections_debug.html` line 2320 documents the superseded flip plan; Recent
Activity still shows 09-29 as today"* is **closed**. v0.7.22 rebuilt that block on 10-02; read at
line 2310–2330 on 10-03, it correctly describes 10-03 as a post-ship read and carries the
`n_excluded_no_counterfactual` caveat. Removed from the open list.

## Related

- [[project_l1_static_blend_v076]] · [[project_10_02_session]] · [[project_10_01_session]]
- [[feedback_apply_flip_invalidates_shadow_verifier]] · [[feedback_shipped_flag_verify_effect]]
- [[feedback_grid_select_halves_stable]] · [[project_collector_memory_leak_hunt]]
