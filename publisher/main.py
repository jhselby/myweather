"""Cloud Function entrypoint for the dashboard-data publisher.

Runs the 6 analysis scripts that publish rollup JSONs to gs://myweather-data/
for the debug page to fetch. Local execution unchanged — this only fires when
Cloud Scheduler hits the HTTP trigger.

Cadence: hourly (0 * * * *) — sits at ~16% of Cloud Functions Gen2 free tier.

Env setup:
    MYWEATHER_CACHE_DIR=/tmp/cache     — writable tmpfs for pair-log downloads
    MYWEATHER_CACHE_MODE=gcs           — read pair log direct from bucket, not curl
    MYWEATHER_OUTPUT_DIR=/tmp/output   — writable tmpfs for local .txt/.json mirror

Each script has its own upload_json call already; we just run them in
sequence and collect status.
"""
import importlib
import logging
import os
import sys
import time
import traceback

# Configure filesystem before importing anything from analysis/
os.environ.setdefault("MYWEATHER_CACHE_DIR", "/tmp/cache")
os.environ.setdefault("MYWEATHER_CACHE_MODE", "gcs")
os.environ.setdefault("MYWEATHER_OUTPUT_DIR", "/tmp/output")

os.makedirs(os.environ["MYWEATHER_CACHE_DIR"], exist_ok=True)
os.makedirs(os.environ["MYWEATHER_OUTPUT_DIR"], exist_ok=True)

# Make `from _cache import ...` work — same trick each analysis script uses.
ANALYSIS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis")
sys.path.insert(0, ANALYSIS_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Order matters: nbm_backstamp_append runs FIRST so all downstream jobs
# that read forecast_error_log_backstamped.jsonl (scoreboard_v2,
# per_field_scoring, nbm_l2_delta_audit, l1_blender_shadow_verify) see
# fresh data within the same publisher tick. After that, mae_over_time
# runs first among the readers because it's the debug page's most-read.
PUBLISHERS = [
    # Incremental appender for the backstamped pair-log. Reads live
    # pair-log's byte HWM, range-downloads new bytes, appends via GCS
    # compose. Keeps all downstream scoring jobs on fresh data without
    # requiring manual `nbm_backstamp` rebuilds. See analysis/nbm_backstamp_append.py.
    "nbm_backstamp_append",
    "mae_over_time",
    "gate_firing_rollup",
    "h_persistence_skill",
    "h_pp_platt_calibration",
    "h_pp_bin_calibration",
    "pp_brier_reliability",
    # Phase 4 scoreboard v2 (2026-08-19) — Prod-vs-best-public rollup
    # + per-field detail. Retires the pre-Phase-4 "vs raw" framing.
    "scoreboard_v2",
    # Per-field two-step scoring (2026-08-19): Selection lift (L1 vs HRRR/NBM)
    # + Correction lift (Prod vs L1) + Total pipeline lift (Prod vs best raw).
    # Under "Current state" on the debug page.
    "per_field_scoring",
    # L2_NBM soundness audit (2026-08-26 v0.6.492) — measures whether the
    # HRRR-delta reconstruction l2_nbm = raw_nbm + (l2_hrrr − raw_hrrr)
    # actually lifts vs raw_nbm by (field, lead-band). Debug page reads
    # the JSON for the L2_NBM soundness tile.
    "nbm_l2_delta_audit",
    # L1 blender shadow-verify (v0.7.0, 2026-09-23) — per curated cell,
    # is the blender's shadow forecast beating what the selector served?
    # Debug page reads the JSON for the L1 blender status tile.
    "l1_blender_shadow_verify",
]


def publish(request):
    """HTTP entrypoint. Cloud Scheduler hits this hourly."""
    results = {}
    started = time.time()
    for name in PUBLISHERS:
        step_start = time.time()
        try:
            # Fresh import per invocation — importlib.reload ensures per-run
            # module state doesn't carry over between Cloud Function instances
            # sharing memory. Cheap for stdlib-only scripts (~ms).
            if name in sys.modules:
                mod = importlib.reload(sys.modules[name])
            else:
                mod = importlib.import_module(name)
            mod.main()
            results[name] = {"status": "ok", "sec": round(time.time() - step_start, 1)}
            logging.info(f"  ✓ {name} ok ({results[name]['sec']}s)")
        except Exception as e:
            results[name] = {
                "status": "fail",
                "sec": round(time.time() - step_start, 1),
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            }
            logging.error(f"  ✗ {name} FAILED: {e}")

    total = round(time.time() - started, 1)
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    fail = len(results) - ok
    summary = {"total_sec": total, "ok": ok, "fail": fail, "results": results}
    logging.info(f"publisher done: {ok} ok, {fail} fail, {total}s")
    # Return 200 even on partial failure — Scheduler will retry the whole
    # batch next hour anyway, and we don't want one broken publisher to
    # gate the healthy ones.
    return (summary, 200)
