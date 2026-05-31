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


def plot_field(pairs, field_short, field_label, field_unit, hilo, out_path):
    """One PNG per field. Each PNG has len(LEADS_TO_PLOT) subplots
    (one per lead), each showing mean error per tide-phase bin."""
    fig, axes = plt.subplots(1, len(LEADS_TO_PLOT),
                             figsize=(3.5 * len(LEADS_TO_PLOT), 3.6),
                             sharey=True)
    if len(LEADS_TO_PLOT) == 1:
        axes = [axes]

    field_pairs = [p for p in pairs if p["field"] == field_short]
    fig.suptitle(f"{field_label} ({field_unit}) — mean forecast error vs tide phase"
                 f"   ·   total pairs: {len(field_pairs):,}", fontsize=11)

    summary_lines = [f"\n=== {field_label} ({field_short}) ==="]

    for ax, lead in zip(axes, LEADS_TO_PLOT):
        bins = defaultdict(list)
        for p in field_pairs:
            if p["lead_h"] != lead:
                continue
            try:
                obs_dt = parse_local(p["obs_time"])
            except ValueError:
                continue
            ph = tide_phase(obs_dt, hilo)
            if ph is None:
                continue
            bin_idx = min(int(ph * N_PHASE_BINS), N_PHASE_BINS - 1)
            bins[bin_idx].append(p["error"])

        xs = (np.arange(N_PHASE_BINS) + 0.5) * (M2_PERIOD_H / N_PHASE_BINS)
        means = [np.mean(bins[i]) if bins[i] else np.nan for i in range(N_PHASE_BINS)]
        counts = [len(bins[i]) for i in range(N_PHASE_BINS)]
        total = sum(counts)

        colors = ["#4aa3ff" if not np.isnan(m) and m >= 0 else "#ef6450"
                  if not np.isnan(m) else "#3a3f4a" for m in means]
        ax.bar(xs, [0 if np.isnan(m) else m for m in means],
               width=(M2_PERIOD_H / N_PHASE_BINS) * 0.9,
               color=colors, alpha=0.75, edgecolor="none")
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_title(f"lead {lead}h (n={total:,})", fontsize=10)
        ax.set_xlabel("hours since prev high tide")
        ax.set_xlim(0, M2_PERIOD_H)
        ax.grid(True, alpha=0.2)
        if ax is axes[0]:
            ax.set_ylabel(f"mean error ({field_unit})")

        summary_lines.append(f"  lead {lead}h: n={total:,}, "
                             f"bin means = "
                             + ", ".join(f"{m:+.2f}" if not np.isnan(m) else "—"
                                         for m in means))

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return summary_lines


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
