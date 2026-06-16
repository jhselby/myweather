
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _cache import cached_path
#!/usr/bin/env python3
"""
Walk-forward L3+L4 on/off validator.

Question: for each of the 12 fields with full L1→L4 coverage, does enabling
Layer 3 (decay correction) and Layer 4 (diurnal correction) actually beat
just stopping at Layer 2?

Background: as of v0.6.27 the L3/L4 over-correcting watch flagged that L3
decay + L4 diurnal looked net-negative for most fields at lead 6h. v0.6.34
restructured L4 (fit on L3 residual, no mean-zero normalization), which may
have resolved it. This validator measures held-out MAE per field for the
three valid enable-state combinations.

Why three combinations, not four:
  Since v0.6.34, L4's coefficients are fit on the residual that L3 leaves
  behind. (L3=off, L4=on) is not a real production option — you'd need to
  refit L4 from scratch, not keep current coefficients. So the matrix is
  (L3,L4) ∈ {(off,off), (on,off), (on,on)}.

Method:
  1. Pull every pair-log row with all of forecast_l2, forecast_l3,
     forecast_l4, observed, lead_h, obs_time.
  2. Train/test split on obs_time (last N days = test).
  3. For each enable state, predict = the corresponding forecast_l*, error =
     |predict - observed|. MAE on test rows.
  4. Per-field winner = enable state with lowest overall test MAE.
  5. Also break out by lead band (0-5, 6-11, 12-23, 24-47) for inspection.

Verdict format: emits a recommended L3_ENABLED / L4_ENABLED set per field,
ready to drop into decay_apply.py.

Output:
  analysis/output/walkforward_l3l4_summary.txt

Run:
    python3 analysis/walkforward_l3l4_validator.py
    python3 analysis/walkforward_l3l4_validator.py --cutoff-days 3
"""
import argparse
import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

FIELDS = ["t", "dp", "h", "ws", "wg", "cc", "sr", "pr", "pa", "ch", "cm", "cl"]
FIELD_LABELS = {
    "t": "Temperature", "dp": "Dew point",  "h": "Humidity",
    "ws": "Wind speed", "wg": "Wind gust",  "cc": "Cloud cover",
    "sr": "Solar rad.", "pr": "Pressure",   "pa": "Precip amt",
    "ch": "Cloud high", "cm": "Cloud mid",  "cl": "Cloud low",
}
LEAD_BINS = 48
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

# An enable state advertises a meaningful win only if it beats the next-simpler
# layer (fewer corrections enabled) by at least this fraction. Prevents picking
# noise-level wins that wouldn't survive a fresh measurement.
MIN_RELATIVE_WIN = 0.02  # 2%


def _fetch_lines(url):
    with open(cached_path(url), 'rb') as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-days", type=float, default=2.0,
                    help="Hold out the last N days as test (default 2.0)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=args.cutoff_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M")
    print(f"Fetching {ERROR_LOG_URL}…")
    print(f"  train <  {cutoff_iso}  <= test")

    # field -> list of (obs_dt, lead, f_l2, f_l3, f_l4, observed)
    train = defaultdict(list)
    test  = defaultdict(list)
    n_in = n_use = 0
    for row in _fetch_lines(ERROR_LOG_URL):
        n_in += 1
        field = row.get("field")
        if field not in FIELDS:
            continue
        lead = row.get("lead_h")
        f_l2 = row.get("forecast_l2")
        f_l3 = row.get("forecast_l3")
        f_l4 = row.get("forecast_l4")
        obs  = row.get("observed")
        obs_t = row.get("obs_time", "")
        if lead is None or f_l2 is None or f_l3 is None or f_l4 is None or obs is None or not obs_t:
            continue
        if not (0 <= lead < LEAD_BINS):
            continue
        try:
            obs_dt = datetime.strptime(obs_t, "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        rec = (obs_dt, int(lead), float(f_l2), float(f_l3), float(f_l4), float(obs))
        if obs_dt < cutoff:
            train[field].append(rec)
        else:
            test[field].append(rec)
        n_use += 1
    n_train = sum(len(v) for v in train.values())
    n_test  = sum(len(v) for v in test.values())
    print(f"  {n_in:,} rows scanned, {n_use:,} usable ({n_train:,} train / {n_test:,} test)")
    print()

    # The validator does NOT refit L3/L4 — those coefficients live in the live
    # decay_fit pipeline. We're measuring how the *already-fitted* coefficients
    # held up on a held-out window. Train rows are reported only for sample-
    # size context; the MAE numbers come from test rows.
    results = {}  # field -> {state: mae, "bands": [...]}
    for field in FIELDS:
        te = test[field]
        if len(te) < 200:
            continue

        # Three enable states, indexed by which forecast_l* they predict from.
        def mae_for(state, rows):
            n = 0; s = 0.0
            for (_, _, f_l2, f_l3, f_l4, obs) in rows:
                if state == "off_off":   pred = f_l2
                elif state == "on_off":  pred = f_l3
                elif state == "on_on":   pred = f_l4
                s += abs(pred - obs); n += 1
            return (s / n) if n else None

        overall = {s: mae_for(s, te) for s in ("off_off", "on_off", "on_on")}
        bands_out = []
        for label, lo, hi in BANDS:
            band_rows = [r for r in te if lo <= r[1] < hi]
            if not band_rows:
                continue
            bands_out.append({
                "label": label,
                "n": len(band_rows),
                "off_off": mae_for("off_off", band_rows),
                "on_off":  mae_for("on_off",  band_rows),
                "on_on":   mae_for("on_on",   band_rows),
            })

        # Decide per-field recommendation. Use a "simpler-wins-ties" rule: an
        # extra layer must beat the simpler state by MIN_RELATIVE_WIN to earn
        # its keep. Walks L3 → L4 in order.
        rec_state = "off_off"
        if overall["on_off"] is not None and overall["off_off"] is not None:
            if (overall["off_off"] - overall["on_off"]) / overall["off_off"] >= MIN_RELATIVE_WIN:
                rec_state = "on_off"
        if rec_state == "on_off" and overall["on_on"] is not None:
            if (overall["on_off"] - overall["on_on"]) / overall["on_off"] >= MIN_RELATIVE_WIN:
                rec_state = "on_on"
        # If L3 didn't earn its keep, L4 doesn't get evaluated (it requires L3).

        results[field] = {
            "n_train": len(train[field]),
            "n_test":  len(te),
            "overall": overall,
            "bands":   bands_out,
            "recommend": rec_state,
        }

    # Build summary
    lines = [
        f"Walk-forward L3+L4 on/off validator — generated {datetime.now().isoformat(timespec='seconds')}",
        f"Train cutoff: {cutoff_iso} UTC  (test = last {args.cutoff_days:.1f}d)",
        f"Enable states: (L3=off, L4=off) | (L3=on, L4=off) | (L3=on, L4=on)",
        f"Recommendation rule: each enabled layer must beat the simpler state by ≥{int(MIN_RELATIVE_WIN*100)}% MAE.",
        "",
        "Per-field held-out MAE (lower = better):",
        "",
    ]
    hdr = f"  {'field':<14} {'n_test':>8}  {'L2 only':>8}  {'L2+L3':>8}  {'L2+L3+L4':>10}  {'recommend':>14}"
    lines.append(hdr)
    lines.append("  " + "-" * (len(hdr) - 2))
    rec_l3 = []
    rec_l4 = []
    for field in FIELDS:
        if field not in results:
            continue
        r = results[field]
        o = r["overall"]
        def fmt(x): return f"{x:>8.3f}" if x is not None else "      -"
        rec_label = {"off_off": "L2 only",
                     "on_off":  "L2 + L3",
                     "on_on":   "L2 + L3 + L4"}[r["recommend"]]
        lines.append(
            f"  {FIELD_LABELS[field]:<14} {r['n_test']:>8,}  "
            f"{fmt(o['off_off'])}  {fmt(o['on_off'])}  {fmt(o['on_on']).rjust(10)}  {rec_label:>14}"
        )
        if r["recommend"] in ("on_off", "on_on"):
            rec_l3.append(field)
        if r["recommend"] == "on_on":
            rec_l4.append(field)

    lines.append("")
    lines.append("Per-field MAE by lead band:")
    for field in FIELDS:
        if field not in results:
            continue
        r = results[field]
        lines.append("")
        lines.append(f"  {FIELD_LABELS[field]}  (recommend: {r['recommend']}):")
        lines.append(f"    {'band':<8} {'n':>7}  {'L2 only':>8}  {'L2+L3':>8}  {'L2+L3+L4':>10}")
        for b in r["bands"]:
            def fmt(x): return f"{x:>8.3f}" if x is not None else "      -"
            lines.append(f"    {b['label']:<8} {b['n']:>7,}  "
                         f"{fmt(b['off_off'])}  {fmt(b['on_off'])}  {fmt(b['on_on']).rjust(10)}")

    lines.append("")
    lines.append("Recommended config (drop into decay_apply.py):")
    lines.append(f"  L3_ENABLED = {{{', '.join(repr(f) for f in rec_l3)}}}")
    lines.append(f"  L4_ENABLED = {{{', '.join(repr(f) for f in rec_l4)}}}")
    if not rec_l3 and not rec_l4:
        verdict = "L3 AND L4 BOTH NET-NEGATIVE on this window — disable both for every field."
    elif rec_l4 == rec_l3 and rec_l3:
        verdict = f"L3 + L4 both earn their keep on {len(rec_l3)} field(s); leave them on there, disable elsewhere."
    else:
        verdict = (f"Per-field split: L3 on for {len(rec_l3)} field(s), "
                   f"L4 on for {len(rec_l4)} field(s). Implement selective enable.")
    lines.append("")
    lines.append(f"Verdict: {verdict}")

    summary_path = os.path.join(OUT_DIR, "walkforward_l3l4_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  ✓ {summary_path}")
    print()
    # Echo the headline table + verdict
    for line in lines:
        if line.startswith("  Temperature") or line.startswith("  Dew point") \
           or line.startswith("  Humidity") or line.startswith("  Wind speed") \
           or line.startswith("  Wind gust") or line.startswith("  Cloud cover") \
           or line.startswith("  Solar rad.") or line.startswith("  Pressure") \
           or line.startswith("  Precip amt") or line.startswith("  Cloud high") \
           or line.startswith("  Cloud mid") or line.startswith("  Cloud low") \
           or line.startswith("  field") or line.startswith("  ---") \
           or line.startswith("Verdict") or line.startswith("  L3_ENABLED") \
           or line.startswith("  L4_ENABLED"):
            print(line)


if __name__ == "__main__":
    main()
