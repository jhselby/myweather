#!/usr/bin/env python3
"""
Hypothesis test: do the decay-curve forecast errors correlate with tide phase?

Standalone analysis — touches nothing in the live app. Downloads
forecast_log.json (4 days of corrected 48h forecast snapshots) and
NOAA harmonic tide predictions for Salem (station 8442645). Synthesizes
forecast-vs-observed pairs by treating each snapshot's lead_h=0 entry as
the "observation" at its run hour, then matching every other snapshot's
lead_h=L entry against it. Bins the errors by M2 tide phase at the obs
time and plots one figure per field showing mean error per phase bin
across several lead times.

If the bars vary significantly across tide-phase bins, the hypothesis
that the decay-curve error tracks the tide cycle is supported.

Usage:
    python3 analysis/tide_hypothesis.py

Outputs:
    analysis/output/tide_hypothesis_<field>.png   (six files, one per field)
    analysis/output/tide_hypothesis_summary.txt   (pair counts + per-bin means)
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

SKIP_CHARTS = os.environ.get("ANALYSIS_NO_CHARTS") == "1"
if not SKIP_CHARTS:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
import numpy as np


FORECAST_LOG_URL = "https://data.wymancove.com/forecast_log.json"
TIDE_STATION = "8442645"  # Salem, MA — same harmonic source the PWA uses
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Fitter / Joiner short keys → display label & units.
FIELDS = [
    ("t",  "Temperature", "°F"),
    ("dp", "Dew point",   "°F"),
    ("h",  "Humidity",    "%"),
    ("ws", "Wind speed",  "mph"),
    ("wg", "Wind gust",   "mph"),
    ("pp", "Precip prob", "%"),
]

# Lead times to render side-by-side per field. Pick a spread that covers
# short-term (where bias/blend still dominate) through long-term decay.
LEADS_TO_PLOT = [6, 12, 18, 24, 36]

M2_PERIOD_H = 12.42        # Principal lunar semi-diurnal tide period
N_PHASE_BINS = 12          # ~1 hour per bin


def parse_local(stamp):
    """Naive ISO minute string ('YYYY-MM-DDTHH:MM') → naive datetime."""
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M")


def _fetch_json(url):
    """urllib.urlopen with a real User-Agent (Cloudflare blocks the default)."""
    req = urllib.request.Request(url, headers={"User-Agent": "myweather-analysis/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def load_snapshots():
    print(f"Fetching {FORECAST_LOG_URL}…")
    data = _fetch_json(FORECAST_LOG_URL)
    snapshots = data.get("snapshots", [])
    print(f"  {len(snapshots):,} snapshots")
    return snapshots


def synthesize_pairs(snapshots):
    """Build (forecast, observed) pairs by treating each snapshot's lead_h=0
    entry as the 'observation' for its run hour, then matching it against any
    other snapshot whose lead_h=L > 0 entry has the same valid_time."""
    # Index snapshots by their lead_h=0 valid_time (which is the run hour
    # rounded to top of hour). Multiple snapshots fall in each hour (~6, at
    # 10-min cadence). We pick one representative per hour to avoid
    # over-counting correlated pairs from near-identical bias estimates.
    obs_by_hour = {}
    for s in snapshots:
        hours = s.get("hours", [])
        if not hours:
            continue
        v0 = hours[0].get("v")
        if v0 and v0 not in obs_by_hour:
            obs_by_hour[v0] = hours[0]

    pairs = []
    for s_old in snapshots:
        run = s_old.get("run")
        if not run:
            continue
        try:
            run_hour_dt = parse_local(run).replace(minute=0, second=0, microsecond=0)
        except ValueError:
            continue
        for h_entry in s_old.get("hours", []):
            v = h_entry.get("v")
            if not v:
                continue
            try:
                v_dt = parse_local(v)
            except ValueError:
                continue
            lead_h = int(round((v_dt - run_hour_dt).total_seconds() / 3600))
            if lead_h <= 0:
                continue
            obs_entry = obs_by_hour.get(v)
            if not obs_entry:
                continue
            for short, _, _ in FIELDS:
                f_val = h_entry.get(short)
                o_val = obs_entry.get(short)
                if f_val is None or o_val is None:
                    continue
                pairs.append({
                    "obs_time": v,
                    "lead_h": lead_h,
                    "field": short,
                    "forecast": float(f_val),
                    "observed": float(o_val),
                    "error": float(f_val) - float(o_val),
                })
    return pairs


def fetch_tide_hilo(start_date, end_date):
    """NOAA harmonic predictions, hi/lo only, for the obs span. Returns a
    list sorted by time of dicts {t: datetime, type: 'H'|'L'}."""
    url = (
        f"https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
        f"?product=predictions&application=myweather_tide_analysis"
        f"&begin_date={start_date}&end_date={end_date}"
        f"&datum=MLLW&station={TIDE_STATION}"
        f"&time_zone=lst_ldt&units=english&interval=hilo&format=json"
    )
    print(f"Fetching tide hi/lo for {start_date}..{end_date} from NOAA…")
    data = _fetch_json(url)
    raw = data.get("predictions", [])
    out = []
    for p in raw:
        try:
            t = datetime.strptime(p["t"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            continue
        out.append({"t": t, "type": p.get("type", "")})
    out.sort(key=lambda x: x["t"])
    print(f"  {len(out)} hi/lo events")
    return out


def tide_phase(obs_dt, hilo):
    """Phase of M2 cycle at obs_dt as a fraction in [0, 1).
    0 = at the most recent high tide; 0.5 = at the next low."""
    prev_high = None
    for ev in hilo:
        if ev["type"] != "H":
            continue
        if ev["t"] <= obs_dt:
            prev_high = ev["t"]
        else:
            break
    if prev_high is None:
        return None
    hours_since = (obs_dt - prev_high).total_seconds() / 3600.0
    return (hours_since % M2_PERIOD_H) / M2_PERIOD_H


N_HOD_BINS = 24            # one bin per hour-of-day
N_HOD_STRATA = 4           # 0-5, 6-11, 12-17, 18-23 — used in the stratified diagnostic
STRATUM_LABELS = ["night (0-5)", "morning (6-11)", "afternoon (12-17)", "evening (18-23)"]
STRATUM_COLORS = ["#4aa3ff", "#7ad97a", "#ff9f4a", "#c084fc"]


def _bin_by_tide(pairs, hilo):
    """Bin (mean error, count) by tide phase. Returns lists of length N_PHASE_BINS."""
    buckets = defaultdict(list)
    for p in pairs:
        try:
            obs_dt = parse_local(p["obs_time"])
        except ValueError:
            continue
        ph = tide_phase(obs_dt, hilo)
        if ph is None:
            continue
        buckets[min(int(ph * N_PHASE_BINS), N_PHASE_BINS - 1)].append(p["error"])
    means = [np.mean(buckets[i]) if buckets[i] else np.nan for i in range(N_PHASE_BINS)]
    counts = [len(buckets[i]) for i in range(N_PHASE_BINS)]
    return means, counts


def _bin_by_hod(pairs):
    """Bin (mean error, count) by hour-of-day. Returns lists of length 24."""
    buckets = defaultdict(list)
    for p in pairs:
        try:
            obs_dt = parse_local(p["obs_time"])
        except ValueError:
            continue
        buckets[obs_dt.hour].append(p["error"])
    means = [np.mean(buckets[i]) if buckets[i] else np.nan for i in range(N_HOD_BINS)]
    counts = [len(buckets[i]) for i in range(N_HOD_BINS)]
    return means, counts


def _bin_by_tide_and_hod_stratum(pairs, hilo):
    """For the diagnostic: bin by tide phase, separately within each
    hour-of-day stratum. Returns dict {stratum_idx: (means, counts)} where
    means/counts are length N_PHASE_BINS."""
    out = {}
    for stratum in range(N_HOD_STRATA):
        lo = stratum * (24 // N_HOD_STRATA)
        hi = lo + (24 // N_HOD_STRATA)
        subset = []
        for p in pairs:
            try:
                obs_dt = parse_local(p["obs_time"])
            except ValueError:
                continue
            if lo <= obs_dt.hour < hi:
                subset.append(p)
        out[stratum] = _bin_by_tide(subset, hilo)
    return out


def _bar_panel(ax, xs, means, width, label_unit, title):
    colors = ["#4aa3ff" if not np.isnan(m) and m >= 0
              else "#ef6450" if not np.isnan(m) else "#3a3f4a" for m in means]
    ax.bar(xs, [0 if np.isnan(m) else m for m in means],
           width=width, color=colors, alpha=0.75, edgecolor="none")
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.2)


def plot_field(pairs, field_short, field_label, field_unit, hilo, out_path):
    """One PNG per field. Two rows × len(LEADS_TO_PLOT) cols:
      row 1: mean error vs tide phase
      row 2: mean error vs hour-of-day
    Same shape + period in both rows → likely confounded with diurnal.
    Pattern in one but not the other → that's the real driver."""
    field_pairs = [p for p in pairs if p["field"] == field_short]
    summary_lines = [f"\n=== {field_label} ({field_short}) ==="]

    if SKIP_CHARTS:
        # Text-only branch: compute bins, return summary, skip matplotlib.
        for lead in LEADS_TO_PLOT:
            lead_pairs = [p for p in field_pairs if p["lead_h"] == lead]
            t_means, _ = _bin_by_tide(lead_pairs, hilo)
            h_means, _ = _bin_by_hod(lead_pairs)
            summary_lines.append(
                f"  lead {lead}h tide bins: "
                + ", ".join(f"{m:+.2f}" if not np.isnan(m) else "—" for m in t_means)
            )
            summary_lines.append(
                f"  lead {lead}h HOD bins:  "
                + ", ".join(f"{m:+.1f}" if not np.isnan(m) else "—" for m in h_means)
            )
        return summary_lines

    n_cols = len(LEADS_TO_PLOT)
    fig, axes = plt.subplots(2, n_cols, figsize=(3.5 * n_cols, 6.4), sharey="row")
    if n_cols == 1:
        axes = axes.reshape(2, 1)

    fig.suptitle(
        f"{field_label} ({field_unit}) — top: error vs tide phase  ·  "
        f"bottom: error vs hour-of-day  ·  total pairs: {len(field_pairs):,}",
        fontsize=11,
    )

    for col, lead in enumerate(LEADS_TO_PLOT):
        lead_pairs = [p for p in field_pairs if p["lead_h"] == lead]
        # Tide phase row
        t_means, t_counts = _bin_by_tide(lead_pairs, hilo)
        xs_t = (np.arange(N_PHASE_BINS) + 0.5) * (M2_PERIOD_H / N_PHASE_BINS)
        _bar_panel(axes[0, col], xs_t, t_means, (M2_PERIOD_H / N_PHASE_BINS) * 0.9,
                   field_unit, f"lead {lead}h tide  (n={sum(t_counts):,})")
        axes[0, col].set_xlim(0, M2_PERIOD_H)
        if col == 0:
            axes[0, col].set_ylabel(f"mean error ({field_unit})")
        axes[0, col].set_xlabel("hours since prev high tide")
        # Hour-of-day row
        h_means, h_counts = _bin_by_hod(lead_pairs)
        xs_h = np.arange(N_HOD_BINS) + 0.5
        _bar_panel(axes[1, col], xs_h, h_means, 0.9, field_unit,
                   f"lead {lead}h hour-of-day  (n={sum(h_counts):,})")
        axes[1, col].set_xlim(0, 24)
        axes[1, col].set_xticks([0, 6, 12, 18, 24])
        if col == 0:
            axes[1, col].set_ylabel(f"mean error ({field_unit})")
        axes[1, col].set_xlabel("local hour")

        summary_lines.append(
            f"  lead {lead}h tide bins: "
            + ", ".join(f"{m:+.2f}" if not np.isnan(m) else "—" for m in t_means)
        )
        summary_lines.append(
            f"  lead {lead}h HOD bins:  "
            + ", ".join(f"{m:+.1f}" if not np.isnan(m) else "—" for m in h_means)
        )

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return summary_lines


def plot_stratified(pairs, field_short, field_label, field_unit, hilo, out_path):
    """Definitive confounding test: for one figure per field, plot tide-phase
    error binned separately within each hour-of-day stratum. One line per
    stratum, on the same axes per lead.

    If the lines have the same shape across all strata → tide is the real
    driver (pattern survives hour-of-day partitioning).
    If lines have very different shapes per stratum → hour-of-day is the
    driver and what looked like a tide pattern is just diurnal aliasing."""
    if SKIP_CHARTS:
        return  # Stratified view is chart-only; no text summary to emit.
    n_cols = len(LEADS_TO_PLOT)
    fig, axes = plt.subplots(1, n_cols, figsize=(3.5 * n_cols, 3.8), sharey=True)
    if n_cols == 1:
        axes = [axes]

    field_pairs = [p for p in pairs if p["field"] == field_short]
    fig.suptitle(
        f"{field_label} ({field_unit}) — tide-phase error stratified by hour-of-day  ·  "
        f"if all lines have the same shape → tide is real",
        fontsize=11,
    )

    xs = (np.arange(N_PHASE_BINS) + 0.5) * (M2_PERIOD_H / N_PHASE_BINS)

    for col, lead in enumerate(LEADS_TO_PLOT):
        lead_pairs = [p for p in field_pairs if p["lead_h"] == lead]
        strata = _bin_by_tide_and_hod_stratum(lead_pairs, hilo)
        ax = axes[col]
        for stratum, (means, counts) in strata.items():
            ax.plot(xs, [m if not np.isnan(m) else None for m in means],
                    marker="o", linewidth=1.5, markersize=3,
                    color=STRATUM_COLORS[stratum],
                    label=f"{STRATUM_LABELS[stratum]}  (n={sum(counts):,})")
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_title(f"lead {lead}h", fontsize=9)
        ax.set_xlabel("hours since prev high tide")
        ax.set_xlim(0, M2_PERIOD_H)
        ax.grid(True, alpha=0.2)
        if col == 0:
            ax.set_ylabel(f"mean error ({field_unit})")
            ax.legend(fontsize=7, loc="best")

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    snapshots = load_snapshots()
    if not snapshots:
        print("No snapshots found — bailing.", file=sys.stderr)
        sys.exit(1)

    print("Synthesizing pairs…")
    pairs = synthesize_pairs(snapshots)
    print(f"  {len(pairs):,} pairs")
    if not pairs:
        print("No pairs synthesized — bailing.", file=sys.stderr)
        sys.exit(1)

    obs_times = sorted({p["obs_time"] for p in pairs})
    earliest, latest = obs_times[0], obs_times[-1]
    print(f"  obs span: {earliest} → {latest}")

    # NOAA wants YYYYMMDD. Pad by ±1 day so the lookup never falls off the end.
    earliest_dt = parse_local(earliest) - timedelta(days=1)
    latest_dt = parse_local(latest) + timedelta(days=1)
    start_date = earliest_dt.strftime("%Y%m%d")
    end_date = latest_dt.strftime("%Y%m%d")

    hilo = fetch_tide_hilo(start_date, end_date)
    if not hilo:
        print("No tide data — bailing.", file=sys.stderr)
        sys.exit(1)

    print("Generating plots…")
    summary = []
    for short, label, unit in FIELDS:
        out_path = os.path.join(OUT_DIR, f"tide_hypothesis_{short}.png")
        summary.extend(plot_field(pairs, short, label, unit, hilo, out_path))
        print(f"  ✓ {out_path}")
        strat_path = os.path.join(OUT_DIR, f"stratified_{short}.png")
        plot_stratified(pairs, short, label, unit, hilo, strat_path)
        print(f"  ✓ {strat_path}")

    summary_path = os.path.join(OUT_DIR, "tide_hypothesis_summary.txt")
    with open(summary_path, "w") as f:
        f.write("Tide-phase hypothesis test — summary\n")
        f.write(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"Snapshots: {len(snapshots):,}\n")
        f.write(f"Synthesized pairs: {len(pairs):,}\n")
        f.write(f"Obs span: {earliest} → {latest}\n")
        f.write(f"Tide station: {TIDE_STATION} (Salem, MA)\n")
        f.write(f"M2 period: {M2_PERIOD_H}h, {N_PHASE_BINS} phase bins\n")
        f.write("\n".join(summary))
        f.write("\n")
    print(f"  ✓ {summary_path}")
    print("\nDone. Open the PNGs in analysis/output/.")


if __name__ == "__main__":
    main()
