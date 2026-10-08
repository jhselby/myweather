---
name: feedback-edit-deploy-division-of-labor
description: "Established division of labor on myweather: Claude edits code directly (never hands Joe scripts for edits). Joe runs deploys, scripts, and the digest. Collector ships have a mandatory wait-a-tick-and-verify step between collector deploy and frontend push."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db0e0f7d-96cd-471b-a038-fb5297164147
  modified: 2026-09-25T12:06:07.101Z
---

# Rule

**Claude edits the code. Joe runs scripts, digest, and deploys.**

- Any code change (JSON curated tables, python fitters, JS, HTML, changelog, version bumps) — Claude uses Edit/Write directly. Do NOT write a python script for Joe to run to perform edits.
- Collector deploys (`make deploy-collector`), analysis scripts, digest generation — Joe runs those.
- **Collector ship sequence:**
  1. Claude edits collector code + curated JSON.
  2. Joe runs `make deploy-collector`.
  3. Wait for the next collector tick (~10 min).
  4. Check the results — GCS `weather_data.json`, logs, whatever the ship touched.
  5. Only then bump version, build.py, commit, push frontend.
- The version bump + changelog + build.py + frontend commit happens AFTER the tick-and-verify, not before.

**Why:** Established pattern for 6 months. Editing via scripts wastes tokens and puts editing responsibility on Joe. Pushing the frontend before verifying the collector tick means shipping a version bump for a change that hasn't been observed working in prod. 09-25 session I did both wrong: gave Joe a python script to run edits, then pushed the whole ship without waiting for the tick.

**How to apply:** On any ship, Claude does the edits inline. On a collector ship, stop after `make deploy-collector` and wait for the tick + Joe's verification signal before touching index.html / changelog / build / push. If Joe types "you do it" or similar, that's the default — not an exception.

**Update 10-07:** Joe asked Claude to run deploys itself ("can't you do it all?"). Claude now runs `make deploy-collector` / `deploy-refitter` / publisher deploys, the tick verify, commit and plain `git push`. The order is unchanged: deploy → tick → verify → bump/commit/push.

Related: [[feedback_deploy_sequence]], [[feedback_verify_completeness_claims]], CLAUDE.md rule 8.
