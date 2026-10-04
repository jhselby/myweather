---
name: feedback-version-bump-convention
description: "MyWeather version numbering — bump the patch number for substantive changes (code, data, real ships); use letter suffixes ONLY for follow-on debug page tweaks to that same substantive ship. NOT \"letter per push.\""
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-04T14:52:02.534Z
---

# Rule

**Patch number** (`v0.6.391` → `v0.6.392`) = a substantive change. New code, ship flip, config change, real work.

**Letter suffix** (`v0.6.392` → `v0.6.392a` → `v0.6.392b`) = follow-on debug page tweaks to the SAME substantive ship. Rare — most substantive changes ship without any follow-ups. Wording tweaks, small visual fixes, sweep-only touches.

**Never** bump letter for the next substantive change. Never invent `aa`/`ab`/`ac` because you ran out of single letters — if you got to `z`, you were misapplying the convention for weeks and each of those should have been a patch bump.

## Why

08-04 session: I inherited a broken pattern from prior sessions where every push got a letter bump (v0.6.390u/v/w/x/y were all substantive). When I hit `z` I invented `aa`/`ab`/`ac`/`ad` and it broke build.py's regex (which was written for the real single-letter convention). Joe: "how did we get to 6.390? With 390 version right?" — pointing out that the version number carries meaning that letters do not.

The real convention had been drifting across dozens of sessions. Fix is to hold the line: substantive = number, tweak = letter, and never invent double letters.

## How to apply

- Before every version bump, ask: is this a real ship or a debug-page-only tweak to the last real ship?
- If real ship → bump the patch number (`391` → `392`).
- If tweak → append a single letter (`392` → `392a` → `392b`).
- If you're about to append `aa` because you ran out of single letters → stop. That means either (a) the last ~26 changes were all mislabeled as tweaks when some were substantive, or (b) you're bumping too eagerly. Either way, bump the patch number instead.
- After ANY version bump, run `python3 build.py` to regenerate `version.json` and `sw.js` CACHE_VERSION. Skipping it leaves the version pill stale — even on localhost. See `[[feedback_build_workflow]]`.

Related: [[feedback_build_workflow]], [[feedback_deploy_sequence]].
