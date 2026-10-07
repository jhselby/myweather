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
"""
import importlib
import json
import logging
import os
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


def _refit_one(spec, now):
    """Run one fitter, guard, publish. Returns a status dict."""
    name = spec["name"]
    out_path = os.path.join(REPO, spec["out"])
    prev = load_json(PREFIX + name)
    if prev is None:
        try:
            with open(out_path) as f:
                prev = json.load(f)   # bundled copy is the baseline on first publish
        except (OSError, json.JSONDecodeError):
            prev = None

    t0 = time.time()
    mod = importlib.import_module(spec["module"])
    getattr(mod, spec["call"])()
    with open(out_path) as f:
        new = json.load(f)

    reason = spec["guard"](new, prev)
    st = {
        "attempted_at": now,
        "fit_seconds": round(time.time() - t0, 1),
        "fitted_at": new.get("fitted_at"),
        "prev_fitted_at": (prev or {}).get("fitted_at"),
    }
    if reason:
        st.update(published=False, reason=reason)
        logging.error(f"refitter: {name} NOT published — {reason}")
        return st
    upload_json(new, PREFIX + name, f"runtime table {name}")
    upload_json(new, f"{PREFIX}history/{now[:10]}/{name}", f"history {name}")
    st.update(published=True, reason=None, summary=spec["summary"](new, prev))
    print(f"refitter: {name} published ({st['summary']})", flush=True)
    return st


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
    upload_json(status, STATUS_PATH, "runtime_tables status")
    return (json.dumps(status, indent=2), 200 if ok else 500, {"Content-Type": "application/json"})
