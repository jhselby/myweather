"""Gate-firing log — Phase (a) of the operator dormancy audit.

Every correction operator (L2 additive, L3 lead-decay, L4 diurnal, Lsr,
Lt, Lc, marine-layer) can be silently dormant even when its config says
"enabled." The class of bug that hid ws L3 for 4 days after v0.6.279: the
skip table shipped, the config had ws in L3_FIELDS, but the classifier
gap meant `_should_skip()` fail-safed to False and NOTHING actually got
skipped — because the writer for `derived.state` didn't exist. Every read
of "is L3 firing on ws in sea_breeze?" would have returned "yes, X cells
skipped" — but the truth was zero.

This module logs, per tick per operator, how many cells actually FIRED
(the correction mutated the output) vs. how many were SKIPPED (skip table
matched) — grouped by field, tagged with the current-tick regime. Phase
(b) will roll up 7 days into `gate_firing_freq.json`. Phase (c) renders
adjacent to the Applicability map on the debug page.

Definition of "fired": the correction code path ran AND changed the value.
Not "would have applied" — actually did.

Per-tick record shape (one row per operator per tick):
  {
    "tick": "2026-07-09T15:07",
    "operator": "L3",
    "regime": "sea_breeze",
    "by_field": {
      "ws": {"fires": 42, "skips": 6},
      "wg": {"fires": 48, "skips": 0},
      ...
    },
    "leads": 48
  }

Buffered per-tick in a module-level list; flushed to GCS via compose at
end of collector.main() (same append pattern as forecast_error_log).
"""
import json
import logging
from datetime import datetime

import pytz

from ..gcs_io import BUCKET, get_client
from ..utils import redact_secrets


TZ = pytz.timezone("America/New_York")
MAIN_PATH = "gate_firing_log.jsonl"
TEMP_PREFIX = "gate_firing_log_temp_"

# Module-level buffer — filled by record_firing() during a tick, drained by
# flush_to_gcs() at end of tick. Cold-start empty; not persisted between ticks.
_TICK_BUFFER = []


def record_firing(operator, regime, by_field, leads=None):
    """Buffer one operator's firing summary for this tick.

    Args:
      operator: short name like "L3", "L4", "Lsr", "Lt", "Lc", "MLC".
      regime: current-tick regime label (e.g. "sea_breeze"), or None if
        the operator doesn't gate on regime.
      by_field: dict {field_short: {"fires": int, "skips": int, ...}}.
      leads: number of forecast leads scanned this tick (usually 48).
    """
    _TICK_BUFFER.append({
        "operator": operator,
        "regime": regime,
        "by_field": {k: dict(v) for k, v in (by_field or {}).items()},
        "leads": leads,
    })


def _tick_stamp():
    """Local-naive minute ISO — matches the shape used elsewhere (obs_time,
    fitted_at, etc.). Truncated to :00 seconds; ticks come on the :07s."""
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def flush_to_gcs():
    """Append buffered per-tick records to gate_firing_log.jsonl in GCS via
    the same compose-append pattern as forecast_error_log. No-op on empty
    buffer. Clears the buffer on both success and failure — a dropped tick
    is preferable to unbounded memory growth if GCS is transiently down."""
    if not _TICK_BUFFER:
        return
    tick = _tick_stamp()
    records = [dict(r, tick=tick) for r in _TICK_BUFFER]
    _TICK_BUFFER.clear()

    try:
        client = get_client()
        bucket = client.bucket(BUCKET)
        main_blob = bucket.blob(MAIN_PATH)
        temp_name = f"{TEMP_PREFIX}{tick.replace(':', '-')}.jsonl"
        temp_blob = bucket.blob(temp_name)
        jsonl_text = "".join(json.dumps(r) + "\n" for r in records)
        temp_blob.upload_from_string(jsonl_text, content_type="application/x-ndjson")
        if main_blob.exists():
            main_blob.compose([main_blob, temp_blob])
            temp_blob.delete()
        else:
            bucket.copy_blob(temp_blob, bucket, MAIN_PATH)
            temp_blob.delete()
        logging.info(f"  ✓ Appended {len(records)} gate-firing rows (tick {tick})")
    except Exception as e:
        logging.error(f"  ✗ gate_firing_log append failed: {redact_secrets(e)}")
        # Best-effort cleanup — the temp blob may or may not exist depending
        # on where the exception fired.
        try:
            temp_blob = bucket.blob(temp_name)
            if temp_blob.exists():
                temp_blob.delete()
        except Exception:
            pass
