"""Runtime tables refit in the cloud, with the bundled file as fallback.

Tables that are meant to track recent data (the selector table, NBM layer
fits, ...) are refit daily by the `myweather-refitter` Cloud Function and
published to gs://myweather-data/runtime_tables/<name>. The collector reads
them through `get()` so a fresh fit takes effect without a deploy and
without the Mac digest. Tables that encode ship decisions (skip tables,
allowlists) stay bundled and are NOT read through here.

Source order for `get(name, bundled_path, validate)`:
  1. the GCS copy, re-checked at most every REFRESH_S seconds (generation
     compare, so an unchanged blob is not re-downloaded),
  2. the last copy that loaded and validated in this process,
  3. the bundled file in weather_collector/data/.
A GCS copy that fails `validate` is ignored (2 or 3 is used) and logged.

`source(name)` reports which one is live, for stamping/telemetry.
"""
import json
import logging
import time

from .gcs_io import BUCKET, get_client

PREFIX = "runtime_tables/"
REFRESH_S = 600

_cache = {}   # name → {"data", "source", "generation", "checked_at"}


def _bundled(name, bundled_path, validate):
    try:
        with open(bundled_path) as f:
            data = json.load(f)
        if validate is None or validate(data) is None:
            return data
        logging.warning(f"  ⚠  runtime_tables: bundled {name} failed validation")
    except (OSError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  runtime_tables: bundled {name} unreadable ({e})")
    return None


def get(name, bundled_path, validate=None):
    """Return the current table dict for `name` (see module docstring).
    `validate(data)` returns None when the table is usable, else a reason."""
    now = time.time()
    ent = _cache.get(name)
    if ent and now - ent["checked_at"] < REFRESH_S:
        return ent["data"]

    gen = ent["generation"] if ent else None
    try:
        blob = get_client().bucket(BUCKET).get_blob(PREFIX + name)
        if blob is not None and blob.generation != gen:
            data = json.loads(blob.download_as_text())
            reason = validate(data) if validate else None
            if reason is None:
                if not ent or ent["source"] != "gcs":
                    print(f"  runtime_tables: {name} ← GCS (fitted_at {data.get('fitted_at')})", flush=True)
                ent = {"data": data, "source": "gcs", "generation": blob.generation, "checked_at": now}
                _cache[name] = ent
                return data
            logging.error(f"  ✗ runtime_tables: GCS {name} rejected: {reason}")
        elif blob is not None and ent:
            ent["checked_at"] = now
            return ent["data"]
    except Exception as e:
        logging.warning(f"  ⚠  runtime_tables: GCS read of {name} failed ({e})")

    if ent:   # keep the last good copy; retry GCS after REFRESH_S
        ent["checked_at"] = now
        return ent["data"]
    data = _bundled(name, bundled_path, validate)
    if data is not None:
        print(f"  runtime_tables: {name} ← bundled (fitted_at {data.get('fitted_at')})", flush=True)
    _cache[name] = {"data": data, "source": "bundled", "generation": None, "checked_at": now}
    return data


def source(name):
    ent = _cache.get(name)
    return ent["source"] if ent else None
