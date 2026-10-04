---
name: already-live-backstops
description: "2026-07-23 v0.6.376. Three machine-enforced fixes for the propose-work-that's-already-done failure mode. Rule (feedback_stated_intent_vs_code_behavior) existed since 07-09 but I kept violating it — six documented instances. Backstops in build_executive_summary.py + build.py automate what memory couldn't reliably deliver."
metadata: 
  node_type: memory
  type: project
  originSessionId: ff24db72-19f0-4e42-bdde-769e1f1f38b6
  modified: 2026-07-24T13:00:53.689Z
---

# Machine-enforced "already-live" backstops (v0.6.376)

## What broke every morning

Scripts emit action verbs (`SHIP`, `PROMOTE`, `IMPLEMENT`, `Move to Stage N`, `STAGE 1 HIT`) for pipelines that are already live. I read the digest verdict as current and propose the action. Six documented instances (07-07, 07-09 AM, 07-09 PM, 07-09 PM, 07-18, 07-23).

Rule existed in [[feedback_stated_intent_vs_code_behavior]]: *any script emitting PROMOTE/KILL/SHIP/RETIRE needs an "already live?" check.* It lived in on-demand memory that didn't fire when I was reading the morning digest, so I kept failing it.

Same class: debug page day-counter drift. I proposed Rule 5 sweeps manually every ~4 days; between sweeps, counters like "Lc day 3/14" fossilized while today was really day 7. My morning summary was based on stale numbers.

## Three fixes shipped v0.6.376

### (1) Script-level STABLE re-check (preferred)

**Where:** the emitting script itself.
**Pattern:** [[project_07_18_session]] references `h_precip_fc_orthogonality.py`'s STABLE re-check as the template. Detect that the target is already live at verdict-emit time; emit `STABLE — <target> already live since <version>` instead of `PROMOTE`.
**Today's fix:** `analysis/h_l3_asymmetric_stage1.py` verdict rewritten from `STAGE 1 HIT — Move to Stage 2 wiring` to `LIVE — table wired since v0.6.366/370`. `bucket()` classifies LIVE as info.

**When to apply:** whenever a script emits an action verb whose target is now live. Ideal fix. Most robust.

### (2) Digest-side backstop registry

**Where:** `analysis/runlog/build_executive_summary.py`.
**Machinery:**
- `KNOWN_LIVE_PIPELINES` dict — `{script_name: {target, since, date}}`.
- `relabel_stable_recheck(name, verdict)` — if script is registered AND verdict contains an action verb (`SHIP`, `PROMOTE`, `IMPLEMENT`, `MOVE TO STAGE`, `STAGE 1 HIT`, `STAGE 2 HIT`, `STAGE 1 PROMOTE`, `STAGE 2 PROMOTE`), rewrites to `STABLE — <target> already live since <since> (<date>). Re-check pass. Original: <original>`. Non-action verdicts (HOLD/MARGIN/KILL/WASH) pass through unchanged.
- `bucket()` now checks for `STABLE` BEFORE `SHIP/PROMOTE/IMPLEMENT` — otherwise the "Original:" tail would re-bucket as promote.
- Main loop calls `relabel_stable_recheck` immediately after `extract_verdict`, tracks relabeled entries in `stable_recheck_relabels`, and emits an `Auto-relabeled STABLE (KNOWN_LIVE_PIPELINES...)` section in the exec summary so nothing is silently suppressed.

**When to extend:** whenever a ship makes a script's action-verb verdict stale. Add an entry:

```python
KNOWN_LIVE_PIPELINES = {
    "<script_name>": {
        "target": "<what shipped>",
        "since": "vX.Y.ZZZ",
        "date": "YYYY-MM-DD",
    },
    ...
}
```

Belt-and-suspenders with (1) — the script-level fix is authoritative; the registry catches scripts not yet fixed.

### (3) Debug page auto-refresh

**Where:** `build.py`.
**Machinery:**
- `SHIP_EVENTS` list — `[{version, date, watch_days}, ...]`.
- `_refresh_debug_page(base_dir)` called from the main build path.
- For each event whose watch is still open (elapsed ≤ watch_days), computes `day_n = elapsed + 1` (convention: day 1 = ship day, matches prior changelog usage) and substitutes on any line containing the version string.
- Uses proximity-limited regex `<version>[^<]{0,140}?\b(day|Day)( )(\d+)/{watch}\b` so that when a changelog line mentions multiple events, each event's iteration only touches its own nearby counter — no cross-clobbering.
- Also bumps the `Last curated:` banner date to today.
- Idempotent — second run is a no-op if all counters are already correct.

**When to extend:** whenever a live-layer change ships that opens a 14-day watch. Add an entry to `SHIP_EVENTS`. Remove after the watch closes cleanly (or leave in place — expired watches are auto-skipped).

## How to use this memory

- Every morning digest read, remember: the machinery is doing the "already live?" check FOR you. If a verdict lands as `STABLE — ... already live since ...`, that's the backstop firing. Read it as "nothing to do here" instead of proposing action.
- If you find yourself about to propose work that seems too obvious ("Move to Stage 2 wiring"), grep first. Add the script to `KNOWN_LIVE_PIPELINES` after fixing the incident so the next morning it self-suppresses.
- If a debug page day counter looks wrong, don't hand-edit — check whether `python3 build.py` has been run recently. If not, run it. If it doesn't fix, the ship event probably isn't in `SHIP_EVENTS` — add it.

## Fix (4) added v0.6.377 — cross-script contradiction registry

**Where:** `analysis/runlog/build_executive_summary.py`.
**Machinery:**
- `TARGET_SCRIPT_GROUPS` dict — `{target: {target_desc, scripts, resolution_note}}`.
- `cross_script_contradictions(current)` — for each target, if the listed scripts have MORE THAN ONE non-info bucket (info skipped so STABLE re-checks don't false-positive), emit a contradiction record.
- Digest output: `⚠ CROSS-SCRIPT CONTRADICTIONS (same target, disagreeing verdicts):` section right after Auto-relabeled STABLE. Lists each script's bucket + verdict + a resolution_note explaining the disagreement.

**Class case:** ch persistence gate — `h_ch_persistence_blend` [promote] vs `h_persistence_skill` [kill]. Both real; blend uses fresh windows, persistence-skill scans full pair log (dilutes post-flip). Resolution note points to [[project_chp_midlead_regression_watch]].

**When to extend:** whenever two scripts on the same live target give opposing verdicts and I acted on one without checking the other. Add an entry with a resolution_note that explains the "expected" disagreement + when to actually worry.

**Design note:** don't over-register. A busy contradictions section becomes noise. Only register targets where the disagreement is common enough that a fresh morning read would miss the second script.

## Registry backfill 2026-07-24

**Failure:** 07-24 morning triage recommended shipping C1h (13 SHIP cells). C1h has been live since v0.6.316 (2026-07-10). Same class as everything above. Backstop was in place but registry had only one entry (`h_l3_asymmetric_stage1`, the seed case). Every other live pipeline emitted its action-verb verdict un-relabeled.

**Root cause of the miss:** shipped the class case, treated the seeded registry as the finished fix. Registry needed to be pre-populated with every currently-live pipeline during the same session.

**Backfilled 07-24:** added `h_c1h_orthogonality`, `h_cloud_disagreement_orthogonality`, `h_ch_persistence_blend`, `h_ch_persistence_blend_stage2`, `lc_fit`. Deliberately NOT added: `walkforward_l3l4_validator` (composite — L4 half live but L3 half proposes real drop of wg/ws; would suppress signal); scripts that already self-emit STABLE (`h_precip_fc_orthogonality`, `cluster_spread_*`).

**Verify:** post-backfill re-run of `build_executive_summary.py` moved four scripts from SHIP-ELIGIBLE / Changed verdicts into the `Auto-relabeled STABLE` section. SHIP-ELIGIBLE now correctly shows only pre_front (THIN-blocked), wind_shift (MIXED), walkforward (L3 drop still gated 2/7).

**Rule going forward:** when shipping a live-layer change, register the emitting script in the same commit. When adding a new script that measures a live target, register at write time.

## Related

- [[feedback_stated_intent_vs_code_behavior]] — the original rule these backstops enforce.
- [[project_07_18_session]] — bright-line rule codified there.
- [[feedback_do_it_right]] — machine-enforced fixes beat process rules memory can't reliably deliver.
- [[feedback_verify_completeness_claims]] — 07-24 registry backfill is another instance: claimed structural fix, shipped incremental fix.
