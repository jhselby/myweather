"""
Pair-log anomaly detector — per-field distribution-shift alert.

Motivated by 2026-07-11 cm Stage 4 flip (project_cm_stage4_degradation). Between
06-27→07-04 (baseline) and 07-04→07-11 (recent), cm HRRR forecast mean went
16% → 47% and MAE 15 → 33 — a boundary-condition-level shift that Stage 4's
mixture check treated as one signal because it was designed to distinguish
weather-mixture-shift from real drift, not to flag WHEN the composition itself
shifts materially. The cm memo's meta-lesson: "Consider adding a companion
diagnostic — 'did the forecast-value distribution shift materially?'"

This script does that. For each field it computes stats on TWO adjacent
pair-log windows and flags fields whose distribution has moved past
threshold. Output feeds the digest exec-summary block.

Two windows (walked from the newest pair):
  recent   = last 7 days
  baseline = prior 21 days (7 → 28 days ago)

Per-field metrics:
  n, forecast_mean, obs_mean, mae, signed_bias
  bin-population fractions in 4 forecast-value quartiles (baseline-defined edges)

Verdict per field:
  ANOMALY  MAE degraded > +50% AND (|Δfc_mean| > 1σ_baseline OR |Δbias| > 5·baseline_bias_std)
  WATCH    MAE degraded > +30% OR |Δfc_mean| > 1σ_baseline OR any bin fraction changed > 15pp
  CLEAN    neither

Run:
    python3 analysis/anomaly_detector.py

Output:
    analysis/output/anomaly_detector.txt
    analysis/output/anomaly_detector.json
"""
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "anomaly_detector.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "anomaly_detector.json")

FIELDS = ["t", "dp", "h", "pr", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "sr", "pp", "pa"]

# Fields with circular (angular) values. For these, `error` is already
# angular-diff-normalized in the pair log (see forecast_error_log.py's
# _circular_diff_deg) so MAE and bias work as-is. Linear-mean and
# quartile-bin stats on raw fc/obs values are MEANINGLESS for circular
# fields (359° and 1° are 2° apart but linear-mean is 180°), so skip
# fc_shift + bin_shift trigger flags — rely on MAE + bias-shift only.
CIRCULAR_FIELDS = {"wd"}

RECENT_DAYS = 7
BASELINE_DAYS = 21   # window immediately prior to recent
MIN_N_PER_WINDOW = 500  # skip fields with insufficient pairs

# Verdict thresholds
MAE_ANOMALY_PCT = 50.0
MAE_WATCH_PCT = 30.0
FC_MEAN_SIGMA_MULTIPLE = 1.0   # |Δmean| > this × baseline_std → shift
BIN_FRAC_SHIFT_PP = 15.0       # any bin fraction moved > this many pp
BIAS_SHIFT_MULTIPLE = 3.0      # |Δbias| > this × baseline signed_err_std → shift


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def stats_dict(vals):
    n = len(vals)
    if n == 0:
        return None
    m = sum(vals) / n
    s = statistics.stdev(vals) if n > 1 else 0.0
    return {"n": n, "mean": m, "std": s}


def quartile_edges(vals):
    """Return three inner quartile cut points (25%, 50%, 75%). Sorts a copy."""
    if not vals:
        return None
    v = sorted(vals)
    n = len(v)
    def q(pct):
        i = int(pct * (n - 1))
        return v[i]
    return q(0.25), q(0.50), q(0.75)


def bin_fractions(vals, edges):
    """Return list of 4 fractions summing to 1.0, per quartile bin using edges."""
    if not vals or edges is None:
        return None
    e1, e2, e3 = edges
    b = [0, 0, 0, 0]
    for v in vals:
        if v <= e1:
            b[0] += 1
        elif v <= e2:
            b[1] += 1
        elif v <= e3:
            b[2] += 1
        else:
            b[3] += 1
    n = len(vals)
    return [x / n for x in b]


def compute():
    """Stream pair log; bucket by field × window. Returns {field: {recent, baseline}}."""
    # First pass to find max timestamp so we can define the windows
    max_ts = None
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            ts = parse_ts(r.get("obs_time"))
            if ts is None:
                continue
            if max_ts is None or ts > max_ts:
                max_ts = ts
    if max_ts is None:
        return None, None, None

    recent_start = max_ts - timedelta(days=RECENT_DAYS)
    baseline_end = recent_start
    baseline_start = baseline_end - timedelta(days=BASELINE_DAYS)

    # Second pass: bucket into windows
    per_field = {f: {"recent_fc": [], "recent_obs": [], "recent_err": [],
                     "baseline_fc": [], "baseline_obs": [], "baseline_err": []}
                 for f in FIELDS}
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in per_field:
                continue
            ts = parse_ts(r.get("obs_time"))
            if ts is None:
                continue
            fc = r.get("forecast")
            ob = r.get("observed")
            err = r.get("error")
            if fc is None or ob is None or err is None:
                continue
            if baseline_start <= ts < baseline_end:
                per_field[f]["baseline_fc"].append(float(fc))
                per_field[f]["baseline_obs"].append(float(ob))
                per_field[f]["baseline_err"].append(float(err))
            elif recent_start <= ts <= max_ts:
                per_field[f]["recent_fc"].append(float(fc))
                per_field[f]["recent_obs"].append(float(ob))
                per_field[f]["recent_err"].append(float(err))
    return per_field, (baseline_start, baseline_end, recent_start, max_ts)


def evaluate(per_field, windows):
    """Return list of per-field verdict dicts + rollup counts."""
    baseline_start, baseline_end, recent_start, max_ts = windows
    fields_out = {}
    for f in FIELDS:
        b_fc = per_field[f]["baseline_fc"]
        b_ob = per_field[f]["baseline_obs"]
        b_er = per_field[f]["baseline_err"]
        r_fc = per_field[f]["recent_fc"]
        r_ob = per_field[f]["recent_obs"]
        r_er = per_field[f]["recent_err"]
        if len(b_fc) < MIN_N_PER_WINDOW or len(r_fc) < MIN_N_PER_WINDOW:
            fields_out[f] = {"verdict": "THIN", "n_baseline": len(b_fc), "n_recent": len(r_fc)}
            continue
        b_fc_s = stats_dict(b_fc)
        r_fc_s = stats_dict(r_fc)
        b_er_s = stats_dict(b_er)
        r_er_s = stats_dict(r_er)
        mae_b = sum(abs(x) for x in b_er) / len(b_er)
        mae_r = sum(abs(x) for x in r_er) / len(r_er)
        mae_pct = (mae_r - mae_b) / mae_b * 100 if mae_b > 0 else 0.0

        d_fc_mean = r_fc_s["mean"] - b_fc_s["mean"]
        d_bias = r_er_s["mean"] - b_er_s["mean"]

        # Bin population: quartiles of baseline forecast distribution
        edges = quartile_edges(b_fc)
        b_frac = bin_fractions(b_fc, edges)
        r_frac = bin_fractions(r_fc, edges)
        max_bin_shift_pp = max(abs(r_frac[i] - b_frac[i]) for i in range(4)) * 100 if b_frac and r_frac else 0.0

        # Trigger flags
        mae_anomaly = mae_pct > MAE_ANOMALY_PCT
        mae_watch = mae_pct > MAE_WATCH_PCT
        bias_shift = (b_er_s["std"] > 0 and abs(d_bias) > BIAS_SHIFT_MULTIPLE * b_er_s["std"])
        # Circular fields have meaningless linear fc_mean / quartile stats — see
        # CIRCULAR_FIELDS comment. Rely on MAE + bias-shift only for those.
        if f in CIRCULAR_FIELDS:
            fc_shift = False
            bin_shift = False
        else:
            fc_shift = (b_fc_s["std"] > 0 and abs(d_fc_mean) > FC_MEAN_SIGMA_MULTIPLE * b_fc_s["std"])
            bin_shift = max_bin_shift_pp > BIN_FRAC_SHIFT_PP

        if mae_anomaly and (fc_shift or bias_shift):
            verdict = "ANOMALY"
        elif mae_watch or fc_shift or bin_shift:
            verdict = "WATCH"
        else:
            verdict = "CLEAN"

        fields_out[f] = {
            "verdict": verdict,
            "n_baseline": len(b_fc),
            "n_recent": len(r_fc),
            "fc_mean_baseline": round(b_fc_s["mean"], 3),
            "fc_mean_recent": round(r_fc_s["mean"], 3),
            "fc_std_baseline": round(b_fc_s["std"], 3),
            "d_fc_mean": round(d_fc_mean, 3),
            "d_fc_mean_sigmas": round(d_fc_mean / b_fc_s["std"], 2) if b_fc_s["std"] > 0 else None,
            "mae_baseline": round(mae_b, 3),
            "mae_recent": round(mae_r, 3),
            "mae_pct_change": round(mae_pct, 1),
            "bias_baseline": round(b_er_s["mean"], 3),
            "bias_recent": round(r_er_s["mean"], 3),
            "d_bias": round(d_bias, 3),
            "max_bin_shift_pp": round(max_bin_shift_pp, 1),
            "bin_frac_baseline": [round(x, 3) for x in b_frac] if b_frac else None,
            "bin_frac_recent": [round(x, 3) for x in r_frac] if r_frac else None,
            "triggers": {
                "mae_anomaly": mae_anomaly,
                "mae_watch": mae_watch,
                "fc_mean_shift": fc_shift,
                "bias_shift": bias_shift,
                "bin_shift": bin_shift,
            },
        }
    return fields_out


def emit(fields_out, windows):
    baseline_start, baseline_end, recent_start, max_ts = windows
    lines = []
    lines.append("=" * 100)
    lines.append("PAIR-LOG ANOMALY DETECTOR — distribution-shift alert per field")
    lines.append("=" * 100)
    lines.append(f"Baseline window: {baseline_start.date().isoformat()} → {baseline_end.date().isoformat()}  ({BASELINE_DAYS}d)")
    lines.append(f"Recent window:   {recent_start.date().isoformat()} → {max_ts.date().isoformat()}  ({RECENT_DAYS}d)")
    lines.append("")
    lines.append(f"Triggers: ANOMALY = MAE > +{MAE_ANOMALY_PCT:.0f}% AND (|Δfc_mean| > {FC_MEAN_SIGMA_MULTIPLE:.1f}σ or bias shift);")
    lines.append(f"          WATCH   = MAE > +{MAE_WATCH_PCT:.0f}% OR |Δfc_mean| > {FC_MEAN_SIGMA_MULTIPLE:.1f}σ OR max bin frac Δ > {BIN_FRAC_SHIFT_PP:.0f}pp;")
    lines.append(f"          CLEAN   = neither.  THIN = < {MIN_N_PER_WINDOW} pairs in either window.")
    lines.append("")

    hdr = (f"{'field':<6}{'verdict':<10}{'n_base':>9}{'n_rec':>8}"
           f"{'fc_μ_b':>9}{'fc_μ_r':>9}{'Δfc_μ':>8}{'Δσ':>7}"
           f"{'MAE_b':>8}{'MAE_r':>8}{'ΔMAE%':>8}{'Δbias':>8}{'binΔpp':>9}")
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for f in FIELDS:
        d = fields_out.get(f) or {}
        v = d.get("verdict", "?")
        if v == "THIN":
            lines.append(f"{f:<6}{v:<10}{d.get('n_baseline',0):>9,}{d.get('n_recent',0):>8,}")
            continue
        mark = "★" if v == "ANOMALY" else ("⚠" if v == "WATCH" else " ")
        sigmas = d.get("d_fc_mean_sigmas")
        sig_txt = f"{sigmas:+.1f}" if sigmas is not None else " --"
        lines.append(
            f"{f:<6}{v+' '+mark:<10}{d['n_baseline']:>9,}{d['n_recent']:>8,}"
            f"{d['fc_mean_baseline']:>+9.2f}{d['fc_mean_recent']:>+9.2f}"
            f"{d['d_fc_mean']:>+8.2f}{sig_txt:>7}"
            f"{d['mae_baseline']:>8.2f}{d['mae_recent']:>8.2f}{d['mae_pct_change']:>+8.1f}"
            f"{d['d_bias']:>+8.2f}{d['max_bin_shift_pp']:>+9.1f}"
        )
    lines.append("")

    n_anom = sum(1 for d in fields_out.values() if d.get("verdict") == "ANOMALY")
    n_watch = sum(1 for d in fields_out.values() if d.get("verdict") == "WATCH")
    n_clean = sum(1 for d in fields_out.values() if d.get("verdict") == "CLEAN")
    n_thin = sum(1 for d in fields_out.values() if d.get("verdict") == "THIN")

    if n_anom:
        anom_fields = sorted(f for f, d in fields_out.items() if d.get("verdict") == "ANOMALY")
        line = f"Verdict: {n_anom} ANOMALY, {n_watch} WATCH, {n_clean} CLEAN, {n_thin} THIN — anomalous: {', '.join(anom_fields)}."
    elif n_watch:
        watch_fields = sorted(f for f, d in fields_out.items() if d.get("verdict") == "WATCH")
        line = f"Verdict: {n_anom} ANOMALY, {n_watch} WATCH, {n_clean} CLEAN, {n_thin} THIN — watch: {', '.join(watch_fields)}."
    else:
        line = f"Verdict: CLEAN — {n_clean} fields nominal ({n_thin} THIN)."
    lines.append(line)
    return "\n".join(lines)


def main():
    per_field, windows = compute()
    if per_field is None:
        print("No pair-log rows found; aborting.", file=sys.stderr)
        return 1
    fields_out = evaluate(per_field, windows)
    text = emit(fields_out, windows)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")

    baseline_start, baseline_end, recent_start, max_ts = windows
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "windows": {
            "baseline_start": baseline_start.isoformat(),
            "baseline_end": baseline_end.isoformat(),
            "recent_start": recent_start.isoformat(),
            "recent_end": max_ts.isoformat(),
        },
        "thresholds": {
            "mae_anomaly_pct": MAE_ANOMALY_PCT,
            "mae_watch_pct": MAE_WATCH_PCT,
            "fc_mean_sigma_multiple": FC_MEAN_SIGMA_MULTIPLE,
            "bin_frac_shift_pp": BIN_FRAC_SHIFT_PP,
            "bias_shift_multiple": BIAS_SHIFT_MULTIPLE,
            "min_n_per_window": MIN_N_PER_WINDOW,
        },
        "fields": fields_out,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
