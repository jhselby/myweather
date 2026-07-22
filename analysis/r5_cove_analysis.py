
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _cache import cached_path
#!/usr/bin/env python3
"""
R5 hypothesis: cove temperature gradient as a function of regime.

Reframed 2026-06-13 after Joe pointed out the Marblehead peninsula geometry:
  - Cove warms +X°F vs inland under S/SE/SW sea breeze (peninsula-lee heating)
  - Cove cools -X°F at 06-10 AM under N/NE/E/NW offshore flow (marine pool)

Reads cove_gradient_log.json (per-tick: delta_wf_inland, wind_dir,
sb_active, hour-of-day). Stratifies by (wind_octant, sb_active, hour)
and reports mean Δ + variance per bin.

Verdict rule (from project_r4_r5_hypotheses memory):
  - Ship a regime-conditional correction if the day-3 pattern (S-half SB
    warming, morning offshore cooling) is stable in the 7-day data:
      * sea-breeze S/SE/SW regime: mean Δ > +1°F with n ≥ 15
      * morning offshore (06-10 EDT, sb_off, N/NE/E/NW): mean Δ < -1°F with n ≥ 15
      * standard deviation of Δ within each bin < 2.5°F (signal > noise)
  - Otherwise close or refine.

Run:
    python3 analysis/r5_cove_analysis.py

Output: analysis/output/r5_cove_summary.txt
"""
import gzip
import json
import os
import statistics
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COVE_LOG_URL = "https://data.wymancove.com/cove_gradient_log.json"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "r5_cove_summary.txt")

OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
S_HALF = {"S", "SE", "SW"}
OFFSHORE = {"N", "NE", "E", "NW"}
MORNING_HOURS = set(range(6, 11))  # 06:00 - 10:59 EDT

# Verdict thresholds
SHIP_SB_WARMING_MIN = 1.0    # °F mean Δ in S-half sea-breeze regime
SHIP_MORNING_COOLING_MAX = -1.0  # °F mean Δ in morning offshore regime
SHIP_MIN_N_PER_BIN = 15      # need at least this many ticks per regime bin
SHIP_MAX_STD = 2.5           # signal-to-noise: stdev under this means signal


def _octant(deg):
    if deg is None:
        return None
    return OCTANTS[int((deg + 22.5) % 360 / 45)]


def _hour(ts):
    # ts is local EDT (collector logs in America/New_York)
    return int(ts[11:13])


def _fetch():
    with open(cached_path(COVE_LOG_URL), 'rb') as resp:
        raw = resp.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = json.loads(gzip.decompress(raw))
    return data.get("entries", [])


def run_analysis():
    entries = _fetch()
    sys.stderr.write(f"  Loaded {len(entries):,} cove log entries\n")

    # Per (sb_active, wind_octant) cell
    by_oct = defaultdict(list)
    # Per hour-of-day, for sb_off only (the diurnal cooling pattern)
    by_hour_sb_off = defaultdict(list)
    # Per (sb_active, wind_octant, hour) for the full lookup table
    by_full = defaultdict(list)

    for e in entries:
        d = e.get("delta_wf_inland")
        if d is None:
            continue
        sb = bool(e.get("sb_active"))
        oct_ = _octant(e.get("wind_dir"))
        if oct_ is None:
            continue
        hour = _hour(e.get("ts", "0000-00-00T00:00"))
        by_oct[(sb, oct_)].append(d)
        if not sb:
            by_hour_sb_off[hour].append(d)
        by_full[(sb, oct_, hour)].append(d)

    def _stats(vals):
        n = len(vals)
        if n == 0:
            return {"n": 0, "mean": None, "std": None, "median": None}
        mean = sum(vals) / n
        std = statistics.stdev(vals) if n > 1 else None
        med = statistics.median(vals)
        return {"n": n, "mean": mean, "std": std, "median": med}

    # Stats per (sb, octant)
    oct_stats = {k: _stats(v) for k, v in by_oct.items()}
    hour_stats = {h: _stats(v) for h, v in by_hour_sb_off.items()}

    # Aggregate the two regimes we care about
    sb_s_half_vals = []
    for o in S_HALF:
        sb_s_half_vals.extend(by_oct.get((True, o), []))
    morning_offshore_vals = []
    for hour in MORNING_HOURS:
        for o in OFFSHORE:
            morning_offshore_vals.extend(by_full.get((False, o, hour), []))

    sb_warming = _stats(sb_s_half_vals)
    morning_cooling = _stats(morning_offshore_vals)

    # Verdict
    sb_ok = (sb_warming["n"] >= SHIP_MIN_N_PER_BIN
             and sb_warming["mean"] is not None
             and sb_warming["mean"] > SHIP_SB_WARMING_MIN
             and (sb_warming["std"] or 0) < SHIP_MAX_STD)
    morning_ok = (morning_cooling["n"] >= SHIP_MIN_N_PER_BIN
                  and morning_cooling["mean"] is not None
                  and morning_cooling["mean"] < SHIP_MORNING_COOLING_MAX
                  and (morning_cooling["std"] or 0) < SHIP_MAX_STD)
    ship = sb_ok and morning_ok

    return {
        "n_entries": len(entries),
        "first_ts": entries[0]["ts"] if entries else None,
        "last_ts": entries[-1]["ts"] if entries else None,
        "oct_stats": oct_stats,
        "hour_stats": hour_stats,
        "sb_warming": sb_warming,
        "morning_cooling": morning_cooling,
        "sb_ok": sb_ok,
        "morning_ok": morning_ok,
        "ship": ship,
    }


def write_summary(result, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append(f"R5 hypothesis — cove temperature gradient by regime")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Window: {result['first_ts']} → {result['last_ts']}  ({result['n_entries']:,} entries)")
    lines.append("")

    # By wind octant and sea-breeze state
    lines.append("Mean Δ(waterfront − inland) °F by (sb_active, wind_octant):")
    lines.append(f"  {'sb':<6} {'wind':<5} {'n':>4} {'mean':>8} {'std':>8} {'median':>8}")
    for (sb, oct_), s in sorted(result["oct_stats"].items()):
        if s["n"] < 3:
            continue
        std_str = f"{s['std']:>8.2f}" if s['std'] is not None else f"{'--':>8}"
        lines.append(f"  {str(sb):<6} {oct_:<5} {s['n']:>4} {s['mean']:>+8.2f} {std_str} {s['median']:>+8.2f}")
    lines.append("")

    # Hour-of-day under sb_off (the cooling regime)
    lines.append("Hour-of-day breakdown for sb_off (the morning marine-cooling regime):")
    lines.append(f"  {'hour':<5} {'n':>4} {'mean Δ':>8} {'std':>8}")
    for h in sorted(result["hour_stats"]):
        s = result["hour_stats"][h]
        if s["n"] < 3:
            continue
        std_str = f"{s['std']:>8.2f}" if s['std'] is not None else f"{'--':>8}"
        lines.append(f"  {h:02d}:00 {s['n']:>4} {s['mean']:>+8.2f} {std_str}")
    lines.append("")

    # Headline regime results
    lines.append("Headline regimes:")
    sb = result["sb_warming"]
    if sb["mean"] is not None:
        std_str = f", std={sb['std']:.2f}°F" if sb['std'] else ""
        lines.append(f"  S/SE/SW sea-breeze warming:  mean Δ = {sb['mean']:+.2f}°F  (n={sb['n']}{std_str})")
        lines.append(f"     → threshold: mean > +{SHIP_SB_WARMING_MIN}°F, n ≥ {SHIP_MIN_N_PER_BIN}, std < {SHIP_MAX_STD}°F  → {'PASS' if result['sb_ok'] else 'FAIL'}")
    mc = result["morning_cooling"]
    if mc["mean"] is not None:
        std_str = f", std={mc['std']:.2f}°F" if mc['std'] else ""
        lines.append(f"  06-10 EDT offshore cooling:  mean Δ = {mc['mean']:+.2f}°F  (n={mc['n']}{std_str})")
        lines.append(f"     → threshold: mean < {SHIP_MORNING_COOLING_MAX}°F, n ≥ {SHIP_MIN_N_PER_BIN}, std < {SHIP_MAX_STD}°F  → {'PASS' if result['morning_ok'] else 'FAIL'}")
    lines.append("")

    if result["ship"]:
        # 2026-07-22 (v0.6.372c): this is a MEASUREMENT-stability verdict, not a
        # ship decision. r5_audit.py is Step 2 (held-out MAE cross-cut vs L4)
        # and is authoritative for the flip. Latest r5_audit read: HOLD — L2's
        # station weighting already absorbs 100% of the gradient (R5+L4 = baseline
        # +0.00% at every regime × band cell). See docstring of r5_audit.py.
        lines.append(f"VERDICT: PATTERN-STABLE — measurement thresholds pass, but ship decision deferred to r5_audit.py.")
        lines.append(f"  Both regime tests pass on the raw gradient log — the bidirectional pattern is real.")
        lines.append(f"  DO NOT flip cove_correction.ENABLED on this verdict alone: r5_audit's held-out MAE")
        lines.append(f"  cross-cut against L4 is what governs shipping. As long as r5_audit says HOLD")
        lines.append(f"  (L2 mesonet already captures the waterfront signal), this stays a diagnostic.")
    else:
        reasons = []
        if not result["sb_ok"]:
            reasons.append("sea-breeze warming regime")
        if not result["morning_ok"]:
            reasons.append("morning offshore cooling regime")
        lines.append(f"VERDICT: HOLD — {' and '.join(reasons)} did not pass threshold.")
        lines.append(f"  Either insufficient n, weak signal, or noisy within-bin.")
        lines.append(f"  Either accumulate more data or refine the correction shape.")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    result = run_analysis()
    out_path = write_summary(result, OUT_PATH)
    sys.stderr.write(f"\nWrote {out_path}\n")
    with open(out_path) as f:
        sys.stdout.write(f.read())
    return 0 if result["ship"] else 1


if __name__ == "__main__":
    sys.exit(main())
