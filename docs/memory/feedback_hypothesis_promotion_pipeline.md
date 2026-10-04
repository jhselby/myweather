---
name: feedback-hypothesis-promotion-pipeline
description: Standard 4-stage promotion pipeline for any new correction-layer hypothesis (R/L). Never skip a stage. Codified by Joe 2026-06-17.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a8831ed-d0ae-48ad-9c90-349a29eadd94
---

Every new correction-layer hypothesis follows the same promotion path. Never skip a stage.

## Stage 0 — Manual exploration

Hypothesis lives only as a script in `analysis/`. Run from Joe's Mac when curious; print to stdout. Uses `_cache.py` for input data.

- Cost: one script.
- Output: terminal printout, sometimes saved to `analysis/output/`.
- Visibility: Joe + Claude in the session.

## Stage 1 — Curated debug-page text

Promising hypothesis gets a hand-typed section on `corrections_debug.html` (and a line on the Status panel). Numbers from the latest manual run are typed into the HTML by hand. Section includes:
- One-line hypothesis statement
- First-read numbers + sample size + date
- Decision rule (e.g., "re-confirm 06-22; if it holds ≥10% effect, promote to Stage 2")
- Pointer to the analysis script

- Cost: HTML edit + version bump.
- Visibility: Joe + any outside reviewer.
- Staleness: numbers are stale between re-edits. Acceptable; the decision rule names a re-confirm date.

## Stage 2 — Auto-wired

Fitter computes the verdict in-process every cycle (twice daily), writes to `shadow_whitelist_log.json` under `conditional_audits[name]`. Debug-page JS reads live. Same pattern R5 and L5 already use:

- Add per-pair accumulators in `decay_fit.py`'s existing pair-stream loop (no second GCS read)
- Compute verdict using same thresholds as the analysis script
- Pass to `log_shadow_recommendation(..., conditional_audits={name: {...}})`
- Add an S1 renderer for the new conditional layer
- Update the Stage-1 debug-page section to point at the live-rendered card

- Cost: ~half day.
- Visibility: live on debug page, refreshes twice daily.
- Promotion gate: only promote from Stage 1 to Stage 2 if Stage 1 first-read passed the decision rule AND a re-confirmation read also passed.

## Stage 3 — Shipped / enabled

Verdict has been auto-wired AND agreed across ≥2 consecutive re-confirmation reads. Flip the `ENABLED` flag (or whitelist entry) in the production processor.

- Cost: one line + redeploy.
- Visibility: changes the actual forecast users see.
- Promotion gate: two consecutive agreeing Stage-2 reads. No exceptions. (R5 went 0→1→2 and got a HOLD verdict — perfect example of why Stage 2 exists.)

## Retirement (the reverse path)

When a hypothesis gets a clear HOLD across ≥2 consecutive Stage-2 reads, retire it back to Stage 0:

1. **Strip auto-wire from `decay_fit.py`**: remove the accumulator, the verdict computation, and the `conditional_audits[name]` write. Stage 2 isn't free — every Fitter cycle pays for accumulators that are never going to flip. Dead weight removed.
2. **Collapse the debug-page card** into a one-line entry in a "Retired hypotheses" section. Format: name, what it tested, verdict, retirement date, link to the script.
3. **Keep the analysis script** on disk forever. Re-run quarterly or when conditions might have shifted (new station, regime classifier change, seasonal turn, etc.).
4. **Keep the memory note** so the reasoning isn't lost. Future-Joe should be able to read "we already checked R5 in June 2026 and it was a HOLD because L2 already captures the signal" without having to re-derive it.

**Why retire instead of leaving auto-wired:** every dead hypothesis we leave running fattens the Fitter cycle for no benefit. Over years, the cycle gets slow + the debug page gets cluttered with HOLD verdicts. Retirement preserves the institutional memory ("we checked that, here's why it didn't work") while reclaiming the cycle cost.

## Why this exists

Catching a problem at Stage 2 costs hours. Catching it at Stage 3 (in production) costs the user's trust. Stages 0 and 1 are cheap; Stage 2 is the expensive auto-wire investment. Promote in order so the expensive work only happens for hypotheses that survived a manual look and a curated re-read.

## How to apply

- New hypothesis from Joe? Start at Stage 0 (write the script).
- Script results look good? Promote to Stage 1 (debug-page text) in the same session.
- First-read decision rule passed AND a later re-read agreed? Promote to Stage 2.
- Two consecutive Stage 2 reads agreed with the decision rule? Promote to Stage 3.

## Related

- [[project-r5-two-step-plan]] — R5 is the canonical example of Stage 2 catching a HOLD verdict that Stage 0/1 missed.
- [[feedback-analysis-cache]] / [[feedback-cache-refresh-policy]] — every Stage 0 script must use `_cache.py`.
- [[project-walkforward-l3l4-validator]] — Stage 0/Stage 2 hybrid for L3/L4 whitelist decisions.
