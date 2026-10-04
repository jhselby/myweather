---
name: sentry-syspath-invocation
description: "Scripts run via `python3 path/to/script.py` set sys.path[0] to the script's directory, NOT repo root. Inline `from analysis._cache import cached_path` (or similar package imports) then fail with ModuleNotFoundError. If the caller has try/except Exception, the failure is invisible — you get 'unavailable' output instead of a crash. Use `python3 -m analysis.runlog.<name>` for anything that imports the analysis package."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 434af779-9797-4cea-bd88-1e0939ffeef0
  modified: 2026-07-31T15:43:12.980Z
---

**Rule:** Any digest-tool script that imports `analysis.*` or `weather_collector.*` packages must be invoked as `python3 -m <fully.qualified.module>`, NOT `python3 path/to/script.py`.

**Why:** `python3 path/to/script.py` sets `sys.path[0]` to the script's directory. If the script has `from analysis._cache import cached_path` inline, `analysis` is not on sys.path — ModuleNotFoundError. When that import is inside a try/except (common for sentries that "silently return None on missing file"), the error is swallowed and you get harmless-looking "unavailable" output instead of a visible crash.

`python3 -m analysis.runlog.<name>` starts with cwd on sys.path (repo root), so `analysis` is importable.

**How to apply:**
- Adding a new sentry / diagnostic to `build_executive_summary.py`? Check the invocation in `run_digest.sh`. Every per-script call uses `-m analysis.<name>` (line 33). The summary+divergence calls used direct-path until v0.6.390e — fixed.
- Writing a new digest-facing tool that does inline `from analysis._cache import cached_path`? Verify end-to-end: run `run_digest.sh` locally and grep the output for the sentry's expected line. Don't just run the sentry function standalone from an interactive Python (where cwd = repo root makes the import work).
- Adding try/except around imports: consider logging the caught exception even if the function returns None. Silent swallowing of ModuleNotFoundError is what turned this into a full-day-blind bug.

**How I hit it (2026-07-30 → 2026-07-31):**
- v0.6.390d shipped layer-shape sentry. Sentry code was correct.
- v0.6.389i shipped regression sentry. Also correct standalone.
- Both silently returned None every digest for 24h. Output said "unavailable" instead of firing.
- Diagnosed morning of 07-31 when I ran the sentry function from a fresh Python (cwd = repo root) and it worked. Then reproduced the failure with `python3 analysis/runlog/build_executive_summary.py` (matches how run_digest.sh called it).
- Fix: swap direct-path to `-m` in `run_digest.sh:85-86`. One-line change per invocation.

**Related pattern warning:** if you add a NEW inline import from a package inside an existing function that was previously stdlib-only, the function may have worked before regardless of invocation. Adding a package import is what activates the sys.path sensitivity. Watch for this on any refactor that adds a package import to an existing sentry/tool.

## Related

- [[project_07_31_session]] — session where this was caught
- [[feedback_verify_writers_for_read_paths]] — same class: writer works standalone, reader path breaks
- [[feedback_stated_intent_vs_code_behavior]] — related; sentry docstring says "silent on missing file" and matched what user saw, hiding that the failure mode was actually import-not-found
