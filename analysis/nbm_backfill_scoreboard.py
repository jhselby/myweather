#!/usr/bin/env python3
"""NBM backfill scoreboard — interim raw-HRRR vs raw-NBM head-to-head.

Purpose: validate the v0.6.432 L1 router's decision at a longer window
than the 14-day scoreboard that seeded it. Router routes t/ws/wd to NBM
at leads ≥6h — we want to see whether NBM's edge holds at ~30d scale
before Phase 4 selector arms on the same premise.

Scope constraint: pair log retains 30 days. Backfill covers ~107 days.
Scoreboard is over the overlap window only (last 30d). Older backfill
cycles have no HRRR baseline in the pair log to compare against.

Method:
  1. List backfill blobs `nbm_backfill/YYYYMMDD_HH.json` in overlap window.
  2. For each (cycle, lead) → NBM value at valid_utc = cycle + lead_h.
  3. Join to pair log by (field, valid_time≈valid_utc, lead_h).
  4. HRRR = pair row's `forecast_l1`; obs = pair row's `observed`.
  5. Aggregate per (field, lead-band) MAE for NBM and HRRR; delta = (HRRR − NBM) / HRRR.
     Positive delta = NBM wins.

Fields scored: the 9 NBM emits (t, dp, ws, wd, wg, sr, cc, ch, h).
Lead bands: 0-5, 6-11, 12-23, 24-47 (matches project convention).
wd MAE uses circular abs diff (min of raw diff and 360 − raw diff).

Runtime:
    python3 -m analysis.nbm_backfill_scoreboard
    MYWEATHER_REFRESH=1 python3 -m analysis.nbm_backfill_scoreboard  # re-download pair log
"""
import gzip
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
BUCKET_NAME = "myweather-data"
BACKFILL_PREFIX = "nbm_backfill/"

FIELDS = ("t", "dp", "ws", "wd", "wg", "sr", "cc", "ch", "h")
ROUTER_FIELDS = {"t", "ws", "wd"}  # v0.6.432 router coverage — flag these in output
WINDOW_DAYS = 30
BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]


def _band_for(lead_h):
    for name, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return name
    return None


def _circular_abs_deg(a, b):
    d = abs(float(a) - float(b)) % 360.0
    return min(d, 360.0 - d)


def _abs_err(field, forecast, obs):
    if field == "wd":
        return _circular_abs_deg(forecast, obs)
    return abs(float(forecast) - float(obs))


def _load_backfill_blobs(window_start_utc):
    """Yield (cycle_utc, blob_dict) for backfill blobs within the window."""
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    count = 0
    for blob in client.list_blobs(BUCKET_NAME, prefix=BACKFILL_PREFIX):
        name = blob.name.split("/")[-1]  # "YYYYMMDD_HH.json"
        if not name.endswith(".json"):
            continue
        try:
            cycle_str = name[:-5]  # YYYYMMDD_HH
            cycle = datetime.strptime(cycle_str, "%Y%m%d_%H").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if cycle < window_start_utc:
            continue
        raw = blob.download_as_bytes()
        # Backfill CF writes gzipped payloads with content_encoding=gzip.
        # download_as_bytes may or may not auto-decompress depending on client
        # version — probe the first bytes.
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        yield cycle, payload
        count += 1
    print(f"  backfill: {count} blobs in {WINDOW_DAYS}-day window", file=sys.stderr)


def _index_pair_log(window_start_local):
    """Return {(field, valid_time_iso, lead_h): (forecast_l1, observed)}.

    valid_time_iso from pair log is local-naive ("YYYY-MM-DDTHH:MM"). We key
    on that string for join purposes and convert backfill valid_utc to the
    same local-naive form.
    """
    idx = {}
    path = cached_path(PAIR_LOG_URL)
    kept = 0
    scanned = 0
    with open(path) as fin:
        for line in fin:
            scanned += 1
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            field = row.get("field")
            if field not in FIELDS:
                continue
            lead_h = row.get("lead_h")
            if lead_h is None or not (0 <= lead_h < 48):
                continue
            vt = row.get("valid_time") or row.get("obs_time")
            if not vt or vt < window_start_local:
                continue
            fc_l1 = row.get("forecast_l1")
            obs = row.get("observed")
            if fc_l1 is None or obs is None:
                continue
            # Round valid_time to top-of-hour (pair log obs_time is minute-
            # precision, backfill will always land on :00 UTC).
            vt_hour = vt[:13] + ":00"
            idx[(field, vt_hour, lead_h)] = (float(fc_l1), float(obs))
            kept += 1
    print(f"  pair log: scanned {scanned:,} rows, indexed {kept:,} in window",
          file=sys.stderr)
    return idx


def aggregate(window_days=WINDOW_DAYS):
    """Reusable join: yields {(field, band): {nbm_abs, hrrr_abs, n}}.

    Returns (acc, matched, unmatched). Selector fitter calls this to get
    the same MAE evidence the printed scoreboard shows.
    """
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    window_start_utc = now_utc - timedelta(days=window_days)
    try:
        import pytz
        TZ = pytz.timezone("America/New_York")
    except ImportError:
        TZ = None
    window_start_local = (now_utc - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M")

    print(f"NBM backfill scoreboard — window {window_days}d from {window_start_utc.isoformat()}",
          file=sys.stderr)
    pair_idx = _index_pair_log(window_start_local)

    acc = defaultdict(lambda: {"nbm_abs": 0.0, "hrrr_abs": 0.0, "n": 0})
    matched = 0
    unmatched = 0
    for cycle_utc, payload in _load_backfill_blobs(window_start_utc):
        leads = payload.get("leads") or {}
        for lead_str, fields_dict in leads.items():
            try:
                lead_h = int(lead_str)
            except (TypeError, ValueError):
                continue
            band = _band_for(lead_h)
            if band is None:
                continue
            valid_utc = cycle_utc + timedelta(hours=lead_h)
            if TZ:
                valid_local = valid_utc.astimezone(TZ).replace(tzinfo=None)
                vt_hour = valid_local.strftime("%Y-%m-%dT%H:00")
            else:
                vt_hour = valid_utc.strftime("%Y-%m-%dT%H:00")
            for field, nbm_val in (fields_dict or {}).items():
                if field not in FIELDS or nbm_val is None:
                    continue
                pair = pair_idx.get((field, vt_hour, lead_h))
                if pair is None:
                    unmatched += 1
                    continue
                fc_l1, obs = pair
                nbm_abs = _abs_err(field, nbm_val, obs)
                hrrr_abs = _abs_err(field, fc_l1, obs)
                bucket = acc[(field, band)]
                bucket["nbm_abs"] += nbm_abs
                bucket["hrrr_abs"] += hrrr_abs
                bucket["n"] += 1
                matched += 1

    return acc, matched, unmatched


def scoreboard():
    acc, matched, unmatched = aggregate()
    print(f"\n  matched {matched:,} (field, cycle, lead) triplets; "
          f"unmatched {unmatched:,}", file=sys.stderr)

    # Emit head-to-head table.
    print("\n" + "=" * 80)
    print(f"NBM vs HRRR — raw-model MAE by (field, lead-band) — {WINDOW_DAYS}d window")
    print("=" * 80)
    print(f"{'field':<6} {'band':<8} {'n':>8}  {'HRRR MAE':>10}  {'NBM MAE':>10}  "
          f"{'NBM lift':>10}  {'router?':<10}")
    print("-" * 80)
    for field in FIELDS:
        for band, _, _ in BANDS:
            b = acc.get((field, band))
            if not b or b["n"] < 20:
                continue
            hrrr_mae = b["hrrr_abs"] / b["n"]
            nbm_mae = b["nbm_abs"] / b["n"]
            lift = 100 * (hrrr_mae - nbm_mae) / hrrr_mae if hrrr_mae > 0 else 0.0
            band_lo = int(band.split("-")[0])
            router_flag = "ROUTED" if field in ROUTER_FIELDS and band_lo >= 6 else ""
            print(f"{field:<6} {band:<8} {b['n']:>8,}  {hrrr_mae:>10.2f}  "
                  f"{nbm_mae:>10.2f}  {lift:>+9.1f}%  {router_flag:<10}")
    print("=" * 80)
    print("Legend: positive NBM lift = NBM wins vs HRRR raw. "
          "ROUTED = v0.6.432 router picks NBM for this (field, lead≥6h).")


if __name__ == "__main__":
    scoreboard()
