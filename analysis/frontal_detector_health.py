"""Frontal-detector calibration health check.

The runtime detector (weather_collector/processors/frontal_detection.py)
uses three signals over a 60-min rolling window:
  - dp_drop ≥ DP_DROP_THRESHOLD (8.0°F)
  - wd_shift ≥ WD_SHIFT_THRESHOLD (60°)
  - press_bounce ≥ PRESSURE_BOUNCE_MIN (0.02 inHg)
Score ≥ 2 fires a passage.

This script sweeps the live frontal_obs_log with the same logic, compares
threshold quantiles to what the atmosphere actually produces, and counts
how many passages the runtime detector missed vs. what the code should
have caught at its own thresholds.

Emits a Verdict: line for the daily digest. Chronic HOLD until the
underlying miscalibration is fixed (see 2026-09-14 investigation).

Run:
    python3 analysis/frontal_detector_health.py
"""
import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Runtime constants — mirrored from frontal_detection.py. If either file
# changes, update the other.
DP_DROP_THRESHOLD    = 4.0  # v0.6.620: lowered 8.0→4.0
WD_SHIFT_THRESHOLD   = 60
PRESSURE_BOUNCE_MIN  = 0.02
WINDOW_MIN           = 60

OBS_URL    = "https://data.wymancove.com/frontal_obs_log.json"
EVENTS_URL = "https://data.wymancove.com/frontal_events_log.json"


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.4.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M")


def _angular_diff(a, b):
    if a is None or b is None:
        return None
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def _window_features(obs):
    """For each tick, compute (ts, dp_drop, wd_shift, press_bounce) using
    the same 60-min window logic frontal_detection.py uses."""
    feats = []
    for i, cur in enumerate(obs):
        now_ts = _parse_ts(cur["ts"])
        cutoff = now_ts - timedelta(minutes=WINDOW_MIN)
        # look back at most 30 slots (60 min at 2-min cadence is plenty)
        win = [e for e in obs[max(0, i - 30):i + 1] if _parse_ts(e["ts"]) >= cutoff]
        if len(win) < 4:
            continue
        win.sort(key=lambda e: e["ts"])
        first, last = win[0], win[-1]
        dp = None
        if first.get("dp") is not None and last.get("dp") is not None:
            dp = first["dp"] - last["dp"]
        wd = _angular_diff(first.get("wd"), last.get("wd"))
        pressures = [e.get("p_inhg") for e in win if e.get("p_inhg") is not None]
        pmin = min(pressures) if pressures else None
        pnow = last.get("p_inhg")
        pb = None
        if pmin is not None and pnow is not None and pnow != pmin:
            pb = pnow - pmin
        feats.append((cur["ts"], dp, wd, pb))
    return feats


def _simulate(feats, dp_thr, wd_thr, pb_thr):
    """Runtime detector logic — count deduped (60-min) passages."""
    hits = []
    for ts, dp, wd, pb in feats:
        s = [
            dp is not None and dp >= dp_thr,
            wd is not None and wd >= wd_thr,
            pb is not None and pb >= pb_thr,
        ]
        if sum(s) >= 2:
            hits.append(ts)
    dedup = []
    for t in hits:
        if dedup and (_parse_ts(t) - _parse_ts(dedup[-1])) <= timedelta(minutes=WINDOW_MIN):
            continue
        dedup.append(t)
    return dedup


def main():
    print("=" * 86)
    print("FRONTAL_DETECTOR_HEALTH — dp/wd/pressure threshold calibration vs observed")
    print("=" * 86)

    try:
        obs = _fetch(OBS_URL).get("entries", [])
    except Exception as e:
        print(f"Failed to fetch obs log: {e}")
        print("Verdict: THIN — obs log unreachable")
        return 0
    obs.sort(key=lambda e: e["ts"])
    if len(obs) < 100:
        print(f"Only {len(obs)} obs entries — insufficient for calibration check.")
        print("Verdict: THIN — obs log too small")
        return 0

    span_h = (_parse_ts(obs[-1]["ts"]) - _parse_ts(obs[0]["ts"])).total_seconds() / 3600
    print(f"\nobs log: {len(obs):,} entries · {obs[0]['ts']} → {obs[-1]['ts']} ({span_h:.0f}h)")

    feats = _window_features(obs)
    dp_vals = [dp for _, dp, _, _ in feats if dp is not None]
    wd_vals = [wd for _, _, wd, _ in feats if wd is not None]
    pb_vals = [pb for _, _, _, pb in feats if pb is not None and pb > 0]

    print("\nSignal distribution vs live thresholds:")
    print(f"  {'signal':<14} {'live_thr':>10} {'max':>8} {'p99.9':>8} {'p99.5':>8} {'p99':>8} {'p95':>8}  status")
    def row(name, thr, vals, unit):
        if not vals:
            print(f"  {name:<14} {thr:>10.2f} {'—':>8} {'—':>8} {'—':>8} {'—':>8} {'—':>8}  no data")
            return
        mx = max(vals)
        p999 = _pct(vals, 99.9); p995 = _pct(vals, 99.5)
        p99 = _pct(vals, 99);    p95 = _pct(vals, 95)
        # Rank threshold against observed
        if thr > mx:
            status = "UNREACHABLE (thr > max observed)"
        elif thr > p999:
            status = "extreme (>p99.9)"
        elif thr > p99:
            status = "tight (>p99)"
        elif thr > p95:
            status = "moderate (>p95)"
        else:
            status = "permissive"
        print(f"  {name:<14} {thr:>10.2f} {mx:>8.2f} {p999:>8.2f} {p995:>8.2f} {p99:>8.2f} {p95:>8.2f}  {status}")
    row("dp_drop °F",    DP_DROP_THRESHOLD,   dp_vals, "°F")
    row("wd_shift °",    WD_SHIFT_THRESHOLD,  wd_vals, "°")
    row("press_bounce",  PRESSURE_BOUNCE_MIN, pb_vals, "inHg")

    # Simulate at current + candidate dp thresholds
    print("\nSimulated 2-of-3 passages / 14 days at candidate dp thresholds "
          f"(wd≥{WD_SHIFT_THRESHOLD}, pb≥{PRESSURE_BOUNCE_MIN}):")
    sim = {}
    thresholds = sorted({2.0, 3.0, 4.0, 5.0, 6.0, 8.0, DP_DROP_THRESHOLD})
    for dp_thr in thresholds:
        sim[dp_thr] = _simulate(feats, dp_thr, WD_SHIFT_THRESHOLD, PRESSURE_BOUNCE_MIN)
        marker = "  ← LIVE" if dp_thr == DP_DROP_THRESHOLD else ""
        print(f"  dp_thr={dp_thr:>4.1f}°F: {len(sim[dp_thr]):>3} events{marker}")

    # Live events log — how many actually fired
    try:
        events = _fetch(EVENTS_URL).get("entries", [])
    except Exception as e:
        events = []
        print(f"\n⚠ events log fetch failed: {e}")
    print(f"\nLive events log: {len(events)} entries")
    types = Counter(e.get("type") for e in events)
    for t, n in types.most_common():
        print(f"  type={t}: {n}")

    live_n = len(events)
    sim_at_live_thr = len(sim[DP_DROP_THRESHOLD])
    miss = sim_at_live_thr - live_n

    # Verdict summary
    dp_max = max(dp_vals) if dp_vals else 0
    dp_unreachable = DP_DROP_THRESHOLD > dp_max
    cold_reachable = any(e.get("type") == "cold" for e in events)

    problems = []
    if dp_unreachable:
        problems.append(f"dp_thr={DP_DROP_THRESHOLD:.1f}°F unreachable (max obs={dp_max:.1f}°F)")
    if not cold_reachable and events:
        problems.append("type='cold' never classified (dp branch unreachable)")
    if miss > 0:
        problems.append(f"runtime missed {miss}/{sim_at_live_thr} candidates")

    print("\n" + "=" * 86)
    if problems:
        print(f"Verdict: HOLD — {'; '.join(problems)}; live={live_n} events / {span_h:.0f}h")
    else:
        print(f"Verdict: CLEAN — thresholds calibrated; live={live_n} events / {span_h:.0f}h")
    print("=" * 86)
    return 0


if __name__ == "__main__":
    sys.exit(main())
