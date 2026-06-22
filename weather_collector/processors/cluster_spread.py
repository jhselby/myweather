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


def _cluster_of(sid):
    if not sid:
        return None
    s = str(sid)
    for c in CLUSTERS:
        if s.startswith(c):
            return c
    return None


def _spread(stations, value_key):
    """Inter-cluster spread = std across per-cluster medians.

    Returns (spread, n_clusters_used, total_n_stations) or (None, ...) if
    fewer than 2 clusters meet MIN_PER_CLUSTER for this field.
    """
    by_cluster = {c: [] for c in CLUSTERS}
    for s in stations:
        c = _cluster_of(s.get("station_id"))
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
