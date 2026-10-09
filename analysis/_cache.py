"""Cache for data.wymancove.com downloads — saves egress cost locally,
and reads from GCS directly when running inside a Cloud Function.

Use:
    from analysis._cache import cached_path
    with open(cached_path(URL)) as f:
        for line in f: ...

Modes:
    local (default): curl the URL, cache in ~/.cache/myweather, 12h TTL.
    Set MYWEATHER_REFRESH=1 to force re-download for any call.

    gcs: set MYWEATHER_CACHE_MODE=gcs. Reads the same file directly from
    the myweather-data bucket into /tmp. Skips curl entirely. Used by the
    publisher Cloud Function.
"""
import os
import subprocess
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("MYWEATHER_CACHE_DIR") or (Path.home() / ".cache" / "myweather"))
MODE = os.environ.get("MYWEATHER_CACHE_MODE", "local")


def cached_path(url, max_age_hours=12, refresh=None):
    """Return local path to url's content, downloading if missing or stale.

    Set MYWEATHER_REFRESH=1 in the env to force a re-download for any call.
    """
    if MODE == "gcs":
        return _gcs_cached_path(url)

    if refresh is None:
        refresh = os.environ.get("MYWEATHER_REFRESH") == "1"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / url.rsplit("/", 1)[-1]
    stale = not path.exists() or (time.time() - path.stat().st_mtime) / 3600 > max_age_hours
    if refresh or stale:
        print(f"  ⇣ caching {url}")
        # Atomic write: curl → .tmp, then os.replace into place. Without this,
        # a parallel reader can iterate the partial file mid-download (caught
        # 2026-06-18 in r5_audit.py — first run reported "0 matched pairs"
        # because it read the cache while it was still streaming).
        #
        # curl instead of urllib.request: urlopen stalls at ~40 MB on large
        # Cloudflare-fronted composite GCS objects (caught 2026-07-17 when
        # the 2.5 GB pair log hung the digest for 25 min at the anomaly
        # detector). curl handles the same fetch at ~24 MB/s.
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            subprocess.run(
                ["curl", "--fail", "--silent", "--show-error",
                 "--retry", "3", "--retry-delay", "2",
                 "--max-time", "1800",
                 "-A", "myweather-analysis/1.0",
                 "-o", str(tmp), url],
                check=True,
            )
            os.replace(tmp, path)
        except BaseException:
            if tmp.exists():
                tmp.unlink()
            raise
    return path


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
PAIR_LOG_BACKSTAMP_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"


def pair_log_paths():
    """Return the list of local paths that together make up the pair-log
    corpus a fitter should stream.

    Today: (1) the live pair log continuously written by the collector,
    plus (2) the one-time historical backstamped file produced by
    `analysis/nbm_backstamp.py`. Both live at stable GCS URLs; the
    backstamped file is a fixed historical artifact that ages out of any
    reasonable retention window on its own (~28 days from the backstamp
    date), so fitters that apply a window filter naturally stop seeing
    its rows once they fall out of scope.

    The two files are NOT disjoint: since the 09-24 backstamp append, the
    backstamped file reaches obs_time 09-24 while the live log starts at
    09-06 (retention-pruned). Every backstamped row at or after the live
    log's first obs_time is an exact duplicate of a live row (verified
    2026-10-07: 285,847 of 285,847). So the second path is a filtered
    copy holding only backstamped rows observed before the live log's
    first row. Without this, 18 fitters double-counted 09-06..09-24.

    Fitters should replace `open(cached_path(PAIR_LOG_URL))` with a loop
    over these paths.
    """
    live = cached_path(PAIR_LOG_URL)
    return [live, _backstamp_before_live(live, cached_path(PAIR_LOG_BACKSTAMP_URL))]


# Pre-swap value = deepest applied HRRR-side layer (the selector classifies
# from `entry[f]` after the HRRR cascade, before swapping NBM in).
# `forecast_l1r` holds it when present.
_RR_FIELDS = ("wd", "ws", "t", "cc")
_RR_HRRR_KEYS = ("forecast_l1r", "forecast_l6", "forecast_l5", "forecast_l4",
                 "forecast_l3", "forecast_l2", "forecast_l1")


class RegimeRuntime:
    """Per-row regime the runtime selector / learned classifier / blender
    looked cells up by (v0.7.35 `state_fc.regime_runtime`).

    `state_fc.regime_synoptic` is reclassified from the post-swap entry and
    disagrees with the runtime label on ~20% of routed hours (10-08). Rows
    written before 10-08 19:37 lack `regime_runtime`; for those, rebuild it
    from the pre-swap HRRR-side wd/ws/t/cc of the same (run_time,
    valid_time). Rebuild matched the stamped label on 130/130 routed t rows
    (10-09) and the runtime label on every unrouted row (10-08).

    Use: call observe(r) on every row of the pass (wd/ws/t/cc rows must be
    seen), then get(r) per row. `counts` reports stamped / rebuilt /
    fallback_synoptic so a fitter can print how its labels were sourced.
    """

    def __init__(self):
        self._pre = {}
        self.counts = {"stamped": 0, "rebuilt": 0, "fallback_synoptic": 0}
        self._cls = None

    def observe(self, r):
        f = r.get("field")
        if f not in _RR_FIELDS:
            return
        for k in _RR_HRRR_KEYS:
            v = r.get(k)
            if v is not None:
                self._pre.setdefault((r.get("run_time"), r.get("valid_time")), {})[f] = v
                return

    def get(self, r):
        sfc = r.get("state_fc") or {}
        rt = sfc.get("regime_runtime")
        if rt:
            self.counts["stamped"] += 1
            return rt
        vt = r.get("valid_time") or ""
        p = self._pre.get((r.get("run_time"), vt))
        if p and len(p) == len(_RR_FIELDS) and len(vt) >= 13:
            if self._cls is None:
                import sys
                root = str(Path(__file__).resolve().parent.parent)
                if root not in sys.path:
                    sys.path.insert(0, root)
                from weather_collector.processors.regime_classifier import classify_synoptic_regime
                self._cls = classify_synoptic_regime
            try:
                reg = self._cls(p["wd"], p["ws"], sfc.get("pressure_in"),
                                sfc.get("pressure_trend_hpa_3h"), int(vt[11:13]),
                                p["t"], cloud_cover=p["cc"])
            except Exception:
                reg = None
            if reg:
                self.counts["rebuilt"] += 1
                return reg
        self.counts["fallback_synoptic"] += 1
        return sfc.get("regime_synoptic")


def _first_obs_time(path):
    """obs_time of the first row. The live log is append-ordered and
    retention-pruned from the front, so its first row is its oldest."""
    with open(path) as f:
        for line in f:
            i = line.find('"obs_time"')
            if i >= 0:
                j = line.find('"', line.find(":", i) + 1)
                return line[j + 1:j + 17]
    return None


def _backstamp_before_live(live_path, backstamp_path):
    """Filtered copy of the backstamped log: rows with obs_time strictly
    before the live log's first obs_time. Rebuilt when either input changes
    (cut moves or backstamp re-downloaded)."""
    cut = _first_obs_time(live_path)
    if not cut:
        return backstamp_path
    out = Path(backstamp_path).with_name(
        f"forecast_error_log_backstamped.before_{cut.replace(':', '')}.jsonl")
    if out.exists() and out.stat().st_mtime >= Path(backstamp_path).stat().st_mtime:
        return out
    for old in out.parent.glob("forecast_error_log_backstamped.before_*.jsonl"):
        old.unlink()
    tmp = out.with_suffix(".jsonl.tmp")
    with open(backstamp_path) as src, open(tmp, "w") as dst:
        for line in src:
            i = line.find('"obs_time"')
            if i < 0:
                continue
            j = line.find('"', line.find(":", i) + 1)
            if line[j + 1:j + 17] < cut:
                dst.write(line)
    os.replace(tmp, out)
    return out


def _gcs_cached_path(url):
    """GCS mode: download the file directly from myweather-data bucket to /tmp.

    Reuses within a single invocation (same process cachehit) but re-downloads
    if the file is older than 5 minutes — guarantees freshness even on warm
    Cloud Function instances that stay hot between hourly runs.
    """
    filename = url.rsplit("/", 1)[-1]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / filename
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < 300
    if fresh:
        return path
    from weather_collector.gcs_io import BUCKET, get_client
    client = get_client()
    blob = client.bucket(BUCKET).blob(filename)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        blob.download_to_filename(str(tmp))
        os.replace(tmp, path)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise
    return path
