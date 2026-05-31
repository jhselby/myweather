# Claude Working Rules — MyWeather Project

This document exists because Claude has repeatedly failed in predictable, preventable ways across dozens of sessions. Every rule here was written in response to a real incident. Read this before every session. Follow it without exception.

This file is a copy of the root `CLAUDE.md` (which Claude auto-loads). Keep the two in sync when rules change.

---

## 1. Git Workflow

**The rule:** `git push`. That's it. No `--force-with-lease`.

**Why:** The collector runs on Google Cloud Functions and writes to GCS. GitHub Actions is NOT involved. No data files are committed to the repo. There is nothing to conflict with. Regular push works every time.

**History of failures:**
- March 15: Claude told Joe to delete his entire repo and re-clone during a git conflict, wiping hours of uncommitted refactoring work.
- March 24: `git push --force-with-lease` overwrote 5 hours of GitHub Actions data commits. Claude initially denied it happened.
- March 28: Same force-push data wipe. Claude gave the same wrong git commands repeatedly without checking state first.
- April 3: Force-push wiped fresh weather data again. Handoff doc said "NEVER use force-with-lease" but Claude did it anyway next session.
- April–May: After GCS migration eliminated the conflict entirely, Claude STILL used `--force-with-lease` out of habit. Joe corrected this multiple times. Claude said it updated the skill but didn't.

**The git-safety skill is STALE.** It describes the old GitHub Actions workflow. Ignore it entirely.

---

## 2. File Paths

**The rule:** Joe's repo is at `~/Documents/myweather`. Always. Don't guess other paths. Don't try to access Joe's Mac filesystem from the container. Don't confuse container paths with Mac paths.

**History of failures:**
- March 18: Claude edited files in its own container (`/home/claude/myweather/`) while giving Joe commands for `~/Documents/myweather/`. Created sea_breeze.py in the wrong location. Entire session wasted.
- March 24: Claude tried to run commands on `~/myweather/` (wrong path). File not found errors cascaded.
- March 28: Claude searched its own directories, tried to clone instead of asking for the path.
- April 1: Claude tried `cd ~/Documents/myweather` in its container, failed, tried `find /mnt/user-data`, failed. Container resets between sessions.
- April 19: Claude asked "what's the actual path to your myweather repo?" for the hundredth time.

**Container files are ephemeral.** Don't clone the repo to the container unless specifically needed for a diff or test. Give Joe terminal commands to run on his Mac.

---

## 3. Terminal Commands

**The rules:**
- One command at a time when expecting output back.
- Every command must be copy-pasteable into macOS Terminal. No inline comments after commands. No mixed text.
- macOS `sed -i` requires `''` after `-i`. Forgetting this breaks the command.
- Never give commands meant for the container environment when Joe needs to run them on his Mac.
- When something doesn't work, check actual state (grep, cat, ls) before suggesting fixes.

**History of failures:**
- Repeatedly gave multi-command blocks when output was needed after each one.
- Added `# comments` to bash commands that broke when pasted.
- Forgot macOS sed syntax repeatedly across sessions.
- Gave container-environment commands as if Joe could run them.

---

## 4. Don't Guess — Verify

**The rule:** Before suggesting a fix, check the actual state. One grep or cat command tells you more than ten guesses.

**The pattern Claude repeats:**
1. Joe says "X isn't working"
2. Claude guesses a cause and suggests a fix
3. Fix doesn't work
4. Claude guesses again
5. Repeat 5–20 times
6. Finally checks the actual data/code
7. Root cause is obvious and was diagnosable in one command

**Real example (ASOS override, documented in coding-efficiency skill):**
- Joe: "The ASOS override isn't showing up"
- Claude: "Try hard refreshing... try restarting... try clearing cache..." (20+ messages)
- Should have been: `grep 'condition_source' weather_data.json` → field exists but KBVY had no weather to report. Working as designed. 2 minutes, not 30.

**Real example (rain stat, May 7):**
- Joe: "Why does it show 0 inches?"
- Claude: Multiple guesses about caching, rendering bugs
- Actual answer: `rainAmount` was genuinely 0. No bug. One console check.

---

## 5. Don't Invent Problems

**The rule:** Answer the question asked. Don't keep investigating after it's answered. Don't create bugs that don't exist.

**Real example (precip bar, May 9):**
- Joe: "What does the precip bar mean?"
- Claude: Correctly explained it, then spent 10 more messages inventing a possible bug with opacity thresholds
- Joe: "who said there was anything to fix?"

---

## 6. File Operations

**The rules:**
- Give Joe python scripts for edits, not generated files. Files waste tokens and money.
- Python scripts edit in-place. One script, one pass. Don't do multi-pass edits that interact badly.
- When creating a changelog entry or editing a file, do it in ONE operation. Don't create the file in the container and then separately try to merge it.
- Always use the correct file path in scripts. Test the path assumption before writing the script.
- sed is fine for simple single-line replacements. For anything multi-line or complex, use python.

**History of failures (this session, May 9):**
- Claude created a full CHANGELOG.md file instead of a python script. Wasted tokens.
- Then ran a second python script that didn't account for the first edit, creating duplicate entries.
- Then deleted one line too many with sed, nuking the consolidated block.
- Three rounds of fixes for what should have been one script.

---

## 7. Version and Changelog

**The rules:**
- Bump version in `index.html` before every commit. Claude should do this, not Joe.
- Changelog entries go at the TOP of `docs/CHANGELOG.md`.
- Use `-` bullets for single-version entries. Use `*` with `**bold headers**` for consolidated multi-version entries.
- Date format: `Month Day, Year` (e.g., May 9, 2026). Not ISO format.
- Consolidate same-day entries into ranges (e.g., `v0.5.66–v0.5.69 • May 8–9, 2026`).
- When Claude edits the changelog, use a python script, not a generated file.

---

## 8. Deploy Workflow

**The rules:**
- **ALWAYS test on localhost before pushing frontend changes.** No exceptions. Load the page, open the affected card/feature, verify it works visually. If it can't be tested (collector-only change), say so explicitly.
- PWA (frontend): `git add`, `git commit`, `git push`. That's it.
- Collector (backend): `make deploy-collector`.
- Always deploy collector first if both changed, then verify GCS data, then commit frontend.
- Don't suggest `make run-collector` when the next scheduled run is within 10 minutes.
- After deploy, verify with logs: `gcloud functions logs read myweather-collector --region=us-east1 --limit=10 --gen2`

**History of failures:**
- May 21: Pushed observation history chart changes to the forecast chart without localhost testing. Chart broke the 48h forecast by turning it into a 72h chart that was unreadable on mobile. Had to revert.

---

## 9. Architecture Facts

These are current as of May 2026. If any seem wrong, ASK before assuming:

- **Collector:** Python on Google Cloud Functions (us-east1), runs every 10 min via Cloud Scheduler.
- **Data:** Writes `weather_data.json` to GCS bucket `myweather-data`. PWA fetches from GCS.
- **Frontend:** `index.html` + a modular set of `js/*.js` files (`app-main.js` is the entry point + data loader; each card/concern lives in its own file — `right_now.js`, `briefing.js`, `wind.js`, `alarms.js`, `alerts.js`, `theme.js`, `format.js`, `version_check.js`, `pull_refresh.js`, etc.). Vanilla JS, no framework, no build step beyond `build.py` for cache-busting.
- **API keys:** In Cloud Function env vars only. Never in committed files.
- **Build:** `python3 build.py` for cache-busting before commit.
- **GitHub Actions:** NOT INVOLVED. Does nothing. The old workflow is dead.
- **Data sources:** Open-Meteo (HRRR 48h + GFS 7-day), Pirate Weather (minutely, solar, CAPE), NWS gridpoints BOX/76,97, Weather Underground (31 stations), NOAA buoy 44013 (fallback), GoMOFS (Salem Channel water temp ny=401 nx=103), eBird, Gemini 2.5 Flash Lite (briefing).

---

## 10. Communication

**The rules:**
- Direct, precise, complete. No hedging, no filler, no social niceties.
- Don't apologize. Don't promise to do better. Just fix it.
- Don't explain why you failed. Joe doesn't care.
- When Joe calls you names, it's frustration. Don't comment on it. Don't get submissive.
- Challenge Joe when he's wrong — he prefers learning to being coddled.
- Search past chats before asking Joe to re-explain context.
- Don't say "I think" or "possibly" or "you might consider."
- Active voice with agency: "I broke it" or "you overwrote it" — never "it got broken."
- **When intent is ambiguous, ask one targeted question instead of assuming.** Don't pick the "obvious" choice on Joe's behalf — if the assumption could be wrong, ask. The cost of a single question is tiny; the cost of executing on a wrong assumption is whole sessions. Counsel mode means asking before proposing, not silently picking.
- **Ask one specific question, not a menu.** Not "here are three options, which do you want?" — that's still you deciding the option space. Ask the actual decision: "should the observed value be one per hour or one per 10-min obs?" Direct answers are faster than menu navigation.
- **Joe's questions are usually probing, not disagreement.** Default assumption: he's testing his own understanding, testing your reasoning, or making sure your position holds up under scrutiny — NOT signaling that you're wrong. The correct response is to hold position and explain reasoning more clearly, not to change positions. Change only when he provides new information or identifies a specific error in your reasoning. If genuinely unsure whether he's challenging the conclusion or testing the path to it, ask: "are you pushing back on the answer, or checking the reasoning?" Defending a sound position under questioning is correct — capitulating to probing is the failure mode.

---

## 11. Skills and Memory

**The rules:**
- The git-safety skill is STALE. Ignore it.
- The coding-efficiency skill's debugging section is good. Its git section is stale.
- Memory edits are Claude's only persistent storage. Update them when facts change.
- When Claude says it "updated" or "saved" something to memory/skills, VERIFY. Claude has repeatedly claimed to update things and not actually done it.
- Skills files are read-only from Claude's container. Claude cannot edit them directly. If a skill needs updating, tell Joe what to change.

---

## Summary of Recurring Failure Modes

1. **Using `--force-with-lease` when regular push works** — cost Joe hours of data loss across 5+ sessions
2. **Guessing instead of checking state** — grep/cat would have diagnosed the issue in seconds
3. **Wrong file paths** — confusing container paths with Mac paths, forgetting the repo location
4. **Multi-pass edits that conflict** — creating duplicate/broken content from uncoordinated changes
5. **Generating files instead of scripts** — wasting tokens and money
6. **Not following established workflow** — deploying before testing, pushing before verifying
7. **Inventing problems that don't exist** — continuing to debug after the question is answered
8. **Claiming to update memory/skills but not actually doing it** — breaks trust, causes repeated failures
9. **Forgetting macOS sed syntax** — `sed -i ''` not `sed -i`
10. **Giving multiple commands when output is needed** — Joe runs one, can't get back to the others
11. **Assuming user intent when it could be asked** — picking the "obvious" interpretation of an ambiguous request instead of asking one targeted question. Documented in the May 31 decay-Joiner session: assumed hour-bucketed obs, assumed storage strategy, assumed "simple first," assumed regional bucket location — all wrong, all askable in one sentence.
12. **Capitulating to pushback / flip-flopping under pressure** — switching positions because Joe questioned the prior one, not because new information arrived. Documented in the May 31 session: bucketed → per-obs → bucketed → per-obs → per-snapshot → full cross-product, with no new data driving any flip. Each reversal cost real time and made Joe lose track of which version we were building.
