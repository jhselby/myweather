---
name: reference-cloud-session-workflow
description: "What a Claude Code CLOUD session can and cannot do for this repo, and the copy-paste pattern for running analysis on the Mac. The container cannot reach data.wymancove.com (proxy 403), so pair-log work runs on Joe's Mac."
metadata:
  node_type: memory
  type: reference
  modified: 2026-10-05T00:00:00.000Z
---

# Cloud session limits (verified 10-04)

- Repo is at `/home/user/myweather` in the container; Joe's repo is `~/Documents/myweather` on the Mac. They only share what is pushed to GitHub.
- **`data.wymancove.com` is blocked** by the environment's network policy (CONNECT tunnel 403). Pair log, `weather_data.json`, `time_series_diagnostic.json` are unreachable. Fix is in the environment's Network access settings (add the host under Allowed domains); until then run pair-log analysis on the Mac.
- No `gcloud`/deploy rights in practice, no localhost testing, no `analysis/output/`. Memory is only visible if it is in the repo (`docs/memory/`, snapshot `69b37ac`); the live memory dir is on the Mac.
- Cloud sessions work on a branch (`claude/relaxed-darwin-7hh03p` this time). A fresh cloud session clones the default branch, so anything not on `main` is invisible to it. Memory written on a branch must be merged/copied to `main` to be seen.
- GitHub access is via MCP tools only (no `gh` CLI for GitHub actions). Plain `git push`, never `--force-with-lease`.

# Pattern: run a cloud-written analysis script on the Mac against the cached pair log

One command, output pasted back (no files left tracked):

```
git fetch origin <branch> && git show FETCH_HEAD:scripts/<name>.py > scripts/<name>.py && python3 scripts/<name>.py
```

The script imports `analysis._cache.cached_path` (12h TTL cache in `~/.cache/myweather`, `MYWEATHER_REFRESH=1` forces a download) and `analysis._prod.prod_error`. Test it in the container on a synthetic pair log first (`MYWEATHER_CACHE_DIR=<dir>` with a pre-placed `forecast_error_log.jsonl` skips curl).
Do NOT put one-off scripts in `analysis/`: `run_digest.sh` runs every `analysis/*.py` daily (use `scripts/`, or `.skip.py`).

# Session-start order that avoids the 10-04 mistakes

1. Read `docs/memory/MEMORY.md` + `feedback_digest_triage_discipline.md` BEFORE restating any digest verdict.
2. Check `git log` / origin state; Joe commits to `main` directly from the Mac.

Related: [[project_10_04_session]] · [[feedback_session_start_load_project_state]] · [[feedback_analysis_skip_naming]] · [[feedback_pair_log_download]]
