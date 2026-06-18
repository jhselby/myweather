"""Regime-transition penalty audit.

Hypothesis: forecast pairs that span a regime change (state_fc.regime_synoptic
!= state_obs.regime_synoptic) show materially worse MAE than pairs where the
predicted and observed regime agree. If true, the system should widen
confidence bands — or fall back to L1 — when the model itself signals a
regime change in the forecast window.

Method:
  1. Stream the pair log (cached). Skip pairs lacking state_fc/state_obs
     (older entries pre-v0.6.29).
  2. Classify each pair:
       - "stable"     : state_fc.regime_synoptic == state_obs.regime_synoptic
       - "transition" : different. Model expected regime A, regime B happened.
  3. Per (field, lead_band, classification): accumulate |error| (the final
     production value — whatever the highest-applied layer produced).
  4. Report MAE side-by-side per band per field, with sample counts and
     transition penalty %.

Verdict: flag fields where transition MAE is ≥10% worse than stable AND each
bucket has ≥200 pairs. Those are candidates for a transition-aware confidence
band (or an L1 fallback during predicted transitions).

Cache:
  Uses analysis/_cache.py. Default 12h freshness. For a decision-grade read,
  run with MYWEATHER_REFRESH=1.
"""
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path, CACHE_DIR

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

BANDS = [
    ("0-5h",   0,  6),
    ("6-11h",  6,  12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]

# Heuristic: fields with native units big enough that a 10% delta is meaningful.
# Apply the SHIP/FLAG threshold per field rather than uniformly.
PENALTY_FLAG_PCT = 10.0
MIN_PAIRS_PER_BUCKET = 200

# Field display labels mirroring the debug page.
FIELD_LABELS = {
    "t": "Temp (°F)", "dp": "Dewpt (°F)", "h": "Humidity (%)",
    "ws": "Wind spd (mph)", "wg": "Wind gust (mph)", "pp": "Precip prob (%)",
    "pr": "Pressure (inHg)", "cc": "Cloud cov (%)", "sr": "Solar (W/m²)",
    "pa": "Precip amt (in)", "cl": "Cloud low (%)", "cm": "Cloud mid (%)",
    "ch": "Cloud high (%)", "wd": "Wind dir (°)",
}


def _band_for(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def _print_cache_age():
    path = CACHE_DIR / ERROR_LOG_URL.rsplit("/", 1)[-1]
    if not path.exists():
        return
    age_h = (time.time() - path.stat().st_mtime) / 3600
    size_mb = path.stat().st_size / (1024 * 1024)
    if age_h < 1:
        age_str = f"{int(age_h * 60)}m ago"
    elif age_h < 48:
        age_str = f"{age_h:.1f}h ago"
    else:
        age_str = f"{age_h / 24:.1f}d ago"
    print(f"📦 pair log: cached {age_str} ({size_mb:.0f} MB)")
    if age_h > 24:
        print("   ⚠ stale — re-run with MYWEATHER_REFRESH=1 for decision-grade output")


def main():
    print("=" * 70)
    print("Regime-transition audit")
    print("=" * 70)
    path = cached_path(ERROR_LOG_URL)
    _print_cache_age()

    # acc[(field, band, transition_bool)] -> [sum_abs_err, n]
    acc = defaultdict(lambda: [0.0, 0])
    total_seen = 0
    skipped_no_state = 0
    transition_count = 0
    stable_count = 0

    with open(path) as f:
        for line in f:
            total_seen += 1
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            sfc = p.get("state_fc")
            sob = p.get("state_obs")
            if not sfc or not sob:
                skipped_no_state += 1
                continue
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            if not rfc or not rob:
                skipped_no_state += 1
                continue

            field = p.get("field")
            lead = p.get("lead_h")
            err = p.get("error")
            if field is None or lead is None or err is None:
                continue
            band = _band_for(lead)
            if band is None:
                continue

            is_transition = (rfc != rob)
            if is_transition:
                transition_count += 1
            else:
                stable_count += 1
            key = (field, band, is_transition)
            acc[key][0] += abs(err)
            acc[key][1] += 1

    print(f"\nPairs scanned: {total_seen:,}")
    print(f"  with state metadata: {transition_count + stable_count:,}")
    print(f"  skipped (no state): {skipped_no_state:,}")
    print(f"  stable: {stable_count:,}  transition: {transition_count:,}")
    if transition_count + stable_count > 0:
        share = 100 * transition_count / (transition_count + stable_count)
        print(f"  transition share: {share:.1f}%")
    print()

    # Print per-field table.
    fields_seen = sorted({k[0] for k in acc.keys()})
    flagged = []
    print(f"{'Field':<18} {'Band':<8} {'Stable MAE':>12} {'Trans MAE':>12} "
          f"{'Penalty %':>11} {'n_st':>8} {'n_tr':>8}")
    print("-" * 80)
    for field in fields_seen:
        label = FIELD_LABELS.get(field, field)
        for band, lo, hi in BANDS:
            s = acc.get((field, band, False), [0.0, 0])
            t = acc.get((field, band, True),  [0.0, 0])
            n_s, n_t = s[1], t[1]
            if n_s == 0 and n_t == 0:
                continue
            mae_s = s[0] / n_s if n_s else float("nan")
            mae_t = t[0] / n_t if n_t else float("nan")
            if n_s and n_t and mae_s > 0:
                pen = 100.0 * (mae_t - mae_s) / mae_s
                pen_str = f"{pen:+7.1f}%"
                if (pen >= PENALTY_FLAG_PCT
                        and n_s >= MIN_PAIRS_PER_BUCKET
                        and n_t >= MIN_PAIRS_PER_BUCKET):
                    pen_str += " ⚠"
                    flagged.append((field, band, pen, n_s, n_t))
            else:
                pen_str = "—"
            print(f"{label:<18} {band:<8} {mae_s:>12.3f} {mae_t:>12.3f} "
                  f"{pen_str:>11} {n_s:>8,} {n_t:>8,}")
        print()

    print("=" * 80)
    if flagged:
        print(f"⚠ {len(flagged)} (field, band) buckets show ≥{PENALTY_FLAG_PCT:.0f}% transition penalty "
              f"with ≥{MIN_PAIRS_PER_BUCKET} pairs/side:")
        for field, band, pen, n_s, n_t in flagged:
            label = FIELD_LABELS.get(field, field)
            print(f"  • {label:<18} {band:<8} penalty {pen:+6.1f}% (n_st={n_s:,} n_tr={n_t:,})")
        print("\nNext step: consider widening confidence bands or L1 fallback")
        print("when state_fc.regime_synoptic differs from current obs regime.")
    else:
        print("No bucket exceeds the penalty threshold with enough samples.")
        print("Either transitions don't materially hurt forecasts (good!), or")
        print("the sample is too small to tell yet — re-run after more data.")


if __name__ == "__main__":
    main()
