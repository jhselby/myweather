"""Per-tick inter-cluster spread metric for C1 axis evaluation.

Computes the std across cluster-median values for temperature and humidity
from the live WU PWS network, grouped by station_id prefix
(KMAMARBL / KMASALEM / KMASWAMP).

High spread = clusters disagree = forecast |error| tends to be inflated
*independently* of R6's regime-transition signal.

Origin: 2026-06-20 cluster-spread hypothesis (backlog item #5). Smoke test
on 2 days returned 18/20 (field, band) combos with Q4/Q1 MAE ratio >= 1.20
(temp 0-5h hit 3.14×). Orthogonality check vs R6 transition flag returned
16/20 ORTHOGONAL — P(transition | high spread) only +9.5 pp above
P(transition | low spread). Cluster-spread is a genuinely new C1 axis,
not a re-detection of regime-transition. This logger captures the metric
each tick so the C1 Stage 3.5 calibration audit (~2026-06-27) has 7+ days
of paired-with-pair-log data.

Stored as cluster_spread_log.json in GCS. 60-day retention.

Stamps `weather_data["cluster_spread"]` for instant inspection on each
tick (debug page can render it later).
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from statistics import median, pstdev

from ..utils import iso_utc_now, redact_secrets

GCS_PATH = "cluster_spread_log.json"
RETENTION_DAYS = 60
CLUSTERS = ("KMAMARBL", "KMASALEM", "KMASWAMP")
MIN_PER_CLUSTER = 2  # need >=2 stations per cluster to compute a stable median


def _cluster_of(station):
    sid = station.get("station_id") if isinstance(station, dict) else station
    if not sid:
        return None
    s = str(sid)
    for c in CLUSTERS:
        if s.startswith(c):
            return c
    return None


def _spread(stations, value_key, cluster_fn=None, clusters=None):
    """Inter-cluster spread = std across per-cluster medians.

    Returns (spread, n_clusters_used, total_n_stations) or (None, ...) if
    fewer than 2 clusters meet MIN_PER_CLUSTER for this field.
    """
    cluster_fn = cluster_fn or _cluster_of
    by_cluster = {c: [] for c in (clusters or CLUSTERS)}
    for s in stations:
        c = cluster_fn(s)
        if not c:
            continue
        v = s.get(value_key)
        if v is None:
            continue
        by_cluster[c].append(v)
    qualifying = {c: vs for c, vs in by_cluster.items() if len(vs) >= MIN_PER_CLUSTER}
    if len(qualifying) < 2:
        return None, len(qualifying), sum(len(vs) for vs in qualifying.values())
    medians = [median(vs) for vs in qualifying.values()]
    n_stations = sum(len(vs) for vs in qualifying.values())
    return round(pstdev(medians), 4), len(qualifying), n_stations


def stamp_and_log(weather_data, wu_data, gcs_client, bucket_name):
    """Compute per-tick cluster spread on temp + humidity. Append to GCS log.
    Best-effort: any failure logs a warning, never raises."""
    if not wu_data:
        return
    stations = wu_data.get("stations") or []
    if not stations:
        return

    try:
        sp_t, n_t, st_t = _spread(stations, "temperature_f")
        sp_h, n_h, st_h = _spread(stations, "humidity_pct")
    except Exception as e:
        logging.warning(f"  ⚠  cluster_spread compute failed: {redact_secrets(e)}")
        return

    if sp_t is None and sp_h is None:
        logging.info(f"  ⊘ cluster_spread: insufficient cluster coverage "
                     f"(t_clusters={n_t}, h_clusters={n_h})")
        return

    ts = iso_utc_now()
    entry = {
        "ts": ts,
        "spread_t": sp_t,
        "spread_h": sp_h,
        "n_clusters_t": n_t,
        "n_clusters_h": n_h,
        "n_stations_t": st_t,
        "n_stations_h": st_h,
    }

    try:
        blob = gcs_client.bucket(bucket_name).blob(GCS_PATH)
        if blob.exists():
            log = json.loads(blob.download_as_text())
        else:
            log = {"entries": []}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
        entries = [e for e in log.get("entries", []) if e.get("ts", "") >= cutoff]
        entries.append(entry)
        blob.upload_from_string(json.dumps({"entries": entries}),
                                content_type="application/json")
    except Exception as e:
        logging.warning(f"  ⚠  cluster_spread log write failed: {redact_secrets(e)}")
        return

    weather_data["cluster_spread"] = {
        "spread_t": sp_t,
        "spread_h": sp_h,
        "n_clusters_t": n_t,
        "n_clusters_h": n_h,
        "ts": ts,
    }
    logging.info(f"  ✓ cluster_spread: t={sp_t}°F (n={n_t} clusters, "
                 f"{st_t} stations), h={sp_h}% (n={n_h})")


# ── Tempest clusters (v0.7.90) ────────────────────────────────────────────
# The WU feed stopped 2026-10-21, so the WU-prefix clusters above no longer
# fill. Tempest stations have numeric ids, so cluster by longitude instead:
# west / central / east of Marblehead (cuts chosen on the 19 live stations:
# 4 west, ~10 central, ~5 east, every cluster >= 2). This is a DIFFERENT
# measure from the WU-cluster spread, so it logs to its own file and stamps
# its own key; the confidence layer keeps reading `cluster_spread` (WU) and
# its Q1/Q23/Q4 cuts are NOT valid for this series until refit on it.
TEMPEST_GCS_PATH = "cluster_spread_tempest_log.json"
TEMPEST_CLUSTERS = ("TP_W", "TP_C", "TP_E")
TP_WEST_LON = -70.885
TP_EAST_LON = -70.855


def _tempest_cluster_of(station):
    lon = station.get("longitude")
    if lon is None:
        return None
    if lon < TP_WEST_LON:
        return "TP_W"
    if lon > TP_EAST_LON:
        return "TP_E"
    return "TP_C"


def stamp_and_log_tempest(weather_data, tempest_data, gcs_client, bucket_name):
    """Same metric as stamp_and_log, from the valid Tempest stations. Best-effort."""
    stations = [st for st in ((tempest_data or {}).get("stations") or [])
                if st.get("valid") is not False and not ((st.get("age_minutes") or 0) > 30)]
    if not stations:
        return
    try:
        sp_t, n_t, st_t = _spread(stations, "temperature_f", _tempest_cluster_of, TEMPEST_CLUSTERS)
        sp_h, n_h, st_h = _spread(stations, "relative_humidity", _tempest_cluster_of, TEMPEST_CLUSTERS)
    except Exception as e:
        logging.warning(f"  ⚠  cluster_spread_tempest compute failed: {redact_secrets(e)}")
        return
    if sp_t is None and sp_h is None:
        return
    ts = iso_utc_now()
    entry = {"ts": ts, "spread_t": sp_t, "spread_h": sp_h, "n_clusters_t": n_t,
             "n_clusters_h": n_h, "n_stations_t": st_t, "n_stations_h": st_h, "source": "tempest"}
    try:
        blob = gcs_client.bucket(bucket_name).blob(TEMPEST_GCS_PATH)
        log = json.loads(blob.download_as_text()) if blob.exists() else {"entries": []}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
        entries = [e for e in log.get("entries", []) if e.get("ts", "") >= cutoff]
        entries.append(entry)
        blob.upload_from_string(json.dumps({"entries": entries}), content_type="application/json")
    except Exception as e:
        logging.warning(f"  ⚠  cluster_spread_tempest log write failed: {redact_secrets(e)}")
        return
    weather_data["cluster_spread_tempest"] = {"spread_t": sp_t, "spread_h": sp_h,
                                              "n_clusters_t": n_t, "n_clusters_h": n_h, "ts": ts}
    logging.info(f"  ✓ cluster_spread_tempest: t={sp_t} (n={n_t} clusters, {st_t} stations), h={sp_h}")
