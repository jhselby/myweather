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
