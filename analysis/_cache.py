"""Local cache for data.wymancove.com downloads — saves egress cost.

Use:
    from analysis._cache import cached_path
    with open(cached_path(URL)) as f:
        for line in f: ...
"""
import os
import subprocess
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "myweather"


def cached_path(url, max_age_hours=12, refresh=None):
    """Return local path to url's content, downloading if missing or stale.

    Set MYWEATHER_REFRESH=1 in the env to force a re-download for any call.
    """
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
