"""Cloud Function entrypoint: daily refit of runtime tables.

Runs each registered fitter (unchanged analysis code) against the pair log
in GCS, checks the result with that table's guard, and publishes it to
gs://myweather-data/runtime_tables/<name>. The collector picks it up through
weather_collector/runtime_tables.py within ~10 minutes — no deploy, no Mac
digest. A table that fails its guard is NOT published; the previous one
stays live and the reason lands in runtime_tables/_status.json (and the
function log at ERROR level, which is visible).

Only tables that are meant to track recent data are registered here.
Tables that encode ship decisions (skip tables, allowlists, LIVE_DEMOTED)
stay in the repo and change only through a ship.

Every published version is also kept at runtime_tables/history/<date>/<name>
so any day's table can be restored by copying it back.

Self-gating tables (streak walkers) keep their history file at
runtime_tables/state/<file>. It is restored before the fit and saved only
when the table publishes, so a refused fit leaves no trace in the streak.

REFITTER_DRY_RUN=1 runs every fitter and guard but uploads nothing.
"""
import importlib
import json
import logging
import os
import runpy
import sys
import time
import traceback
from datetime import datetime, timezone

os.environ.setdefault("MYWEATHER_CACHE_DIR", "/tmp/cache")
os.environ.setdefault("MYWEATHER_CACHE_MODE", "gcs")
os.environ.setdefault("MYWEATHER_OUTPUT_DIR", "/tmp/output")
os.makedirs(os.environ["MYWEATHER_CACHE_DIR"], exist_ok=True)
os.makedirs(os.environ["MYWEATHER_OUTPUT_DIR"], exist_ok=True)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "analysis"))

from weather_collector.gcs_io import BUCKET, get_client, load_json, upload_json  # noqa: E402
from weather_collector.runtime_tables import PREFIX  # noqa: E402
from refitter.tables import TABLES  # noqa: E402

STATUS_PATH = PREFIX + "_status.json"
STATE_PREFIX = PREFIX + "state/"
DRY_RUN = os.environ.get("REFITTER_DRY_RUN") == "1"


def _run_step(step):
    """Run one fitter step: call a function, or run the module as __main__
    with argv the way the digest does. A SystemExit is a normal finish (some
    scripts exit non-zero on a HOLD verdict); the guard judges the output."""
    if "call" in step:
        getattr(importlib.import_module(step["module"]), step["call"])()
        return
    saved = sys.argv
    sys.argv = [step["module"]] + list(step.get("argv") or [])
    try:
        runpy.run_module(step["module"], run_name="__main__", alter_sys=False)
    except SystemExit:
        pass
    finally:
        sys.argv = saved


def _restore_state(spec):
    for rel in spec.get("state") or ():
        data = load_json(STATE_PREFIX + os.path.basename(rel))
        if data is not None:   # else keep the bundled copy (first run)
            with open(os.path.join(REPO, rel), "w") as f:
                json.dump(data, f, indent=2)


def _save_state(spec):
    for rel in spec.get("state") or ():
        with open(os.path.join(REPO, rel)) as f:
            upload_json(json.load(f), STATE_PREFIX + os.path.basename(rel), f"state {rel}")


def _refit_one(spec, now):
    """Run one table's fitter steps, guard, publish. Returns a status dict.
    On refusal the previous table is put back at `out` so later entries
    that read it (e.g. the Lc gate reads the Lc table) see the live copy."""
    name = spec["name"]
    out_path = os.path.join(REPO, spec["out"])
    prev = load_json(PREFIX + name)
    if prev is None:
        try:
            with open(out_path) as f:
                prev = json.load(f)   # bundled copy is the baseline on first publish
        except (OSError, json.JSONDecodeError):
            prev = None
    _restore_state(spec)

    t0 = time.time()
    mtime = os.path.getmtime(out_path) if os.path.exists(out_path) else None
    try:
        for step in spec["steps"]:
            _run_step(step)
        if not os.path.exists(out_path) or os.path.getmtime(out_path) == mtime:
            raise RuntimeError(f"fitter did not write {spec['out']}")
        with open(out_path) as f:
            new = json.load(f)
        reason = spec["guard"](new, prev)
    except Exception:
        _put_back(out_path, prev)
        raise

    stamp = new.get("fitted_at") or new.get("generated_at") or new.get("generated")
    st = {
        "attempted_at": now,
        "fit_seconds": round(time.time() - t0, 1),
        "fitted_at": stamp,
        "prev_fitted_at": (prev or {}).get("fitted_at") or (prev or {}).get("generated_at")
                          or (prev or {}).get("generated"),
    }
    if reason:
        _put_back(out_path, prev)
        st.update(published=False, reason=reason)
        logging.error(f"refitter: {name} NOT published — {reason}")
        return st
    summary = spec["summary"](new, prev)
    if DRY_RUN:
        st.update(published=False, reason="dry run", summary=summary)
        print(f"refitter: {name} would publish ({summary})", flush=True)
        return st
    upload_json(new, PREFIX + name, f"runtime table {name}")
    upload_json(new, f"{PREFIX}history/{now[:10]}/{name}", f"history {name}")
    _save_state(spec)
    st.update(published=True, reason=None, summary=summary)
    print(f"refitter: {name} published ({summary})", flush=True)
    return st


def _put_back(out_path, prev):
    if prev is not None:
        with open(out_path, "w") as f:
            json.dump(prev, f, indent=2)


def refit(request):
    """HTTP entrypoint. Cloud Scheduler hits this once a day."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    status = load_json(STATUS_PATH, default={}) or {}
    status.setdefault("tables", {})
    ok = True
    for spec in TABLES:
        try:
            st = _refit_one(spec, now)
        except Exception as e:
            st = {"attempted_at": now, "published": False,
                  "reason": f"fitter crashed: {e.__class__.__name__}: {e}"}
            logging.error(f"refitter: {spec['name']} crashed\n{traceback.format_exc()}")
        prev_st = status["tables"].get(spec["name"], {})
        if st.get("published"):
            st["last_published_at"] = now
        else:
            ok = False
            st["last_published_at"] = prev_st.get("last_published_at")
        status["tables"][spec["name"]] = st
    status["last_run_at"] = now
    status["last_run_ok"] = ok
    if DRY_RUN:
        print(json.dumps(status, indent=2))
        return (json.dumps(status, indent=2), 200 if ok else 500, {"Content-Type": "application/json"})
    upload_json(status, STATUS_PATH, "runtime_tables status")
    return (json.dumps(status, indent=2), 200 if ok else 500, {"Content-Type": "application/json"})
