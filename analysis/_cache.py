"""Local cache for data.wymancove.com downloads — saves egress cost.

Use:
    from analysis._cache import cached_path
    with open(cached_path(URL)) as f:
        for line in f: ...
"""
import os
import time
import urllib.request
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
        req = urllib.request.Request(url, headers={"User-Agent": "myweather-analysis/1.0"})
        with urllib.request.urlopen(req, timeout=1800) as r, open(path, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    return path
