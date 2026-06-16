"""Preview the new L2 τ fitter output against the cached pair log.

Mirrors the train/test logic from weather_collector/processors/decay_fit.py
(the L2 block of fit_decay_corrections), but runs locally so we don't have
to wait for the next 15:xx fit cycle to know whether the new code produces
sensible output. Writes a preview l2_decay.json to analysis/output/ so we
can compare against what the live fitter will eventually publish.
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "l2_decay_preview.json")

# Mirror decay_fit.py constants exactly.
L2_TAU_FIELDS = ("t", "h", "pr", "ws", "wg")
L2_TAU_GRID = (0.5, 1, 2, 3, 4, 6, 8, 12, 18, 24, 36, 60, 120, 240, 1e9)
L2_HELDOUT_DAYS = 2.0
L2_DEFAULT_TAUS = {"t": 4.0, "h": 240.0, "pr": 12.0}
L2_TAU_MIN_PAIRS = 500
LEAD_BINS = 48
RETENTION_DAYS = 30.0
TAU_DAYS = 14.0


def main():
    now = datetime.utcnow().replace(microsecond=0)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M")
    print(f"Reading cached pair log; retention cutoff {cutoff_iso}; "
          f"held-out window = last {L2_HELDOUT_DAYS} days")

    l2_train = defaultdict(list)
    l2_test  = defaultdict(list)

    n_total = 0
    n_kept = 0
    with open(cached_path(ERROR_LOG_URL), "rb") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            n_total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            obs_time = row.get("obs_time", "")
            if obs_time < cutoff_iso:
                continue
            field = row.get("field")
            lead_h = row.get("lead_h")
            if field not in L2_TAU_FIELDS or lead_h is None:
                continue
            if not (0 <= lead_h < LEAD_BINS):
                continue
            e1 = row.get("error_l1")
            e2 = row.get("error_l2")
            if e1 is None or e2 is None:
                continue
            try:
                obs_dt = datetime.strptime(obs_time, "%Y-%m-%dT%H:%M")
            except ValueError:
                continue
            n_kept += 1
            age_days = max(0.0, (now - obs_dt).total_seconds() / 86400.0)
            w = math.exp(-age_days / TAU_DAYS)
            e1f = float(e1)
            bias = float(e2) - e1f   # err_l1 + 1.0*bias == err_l2
            pair = (lead_h, e1f, bias, w)
            if age_days < L2_HELDOUT_DAYS:
                l2_test[field].append(pair)
            else:
                l2_train[field].append(pair)
    print(f"  scanned {n_total:,} rows, kept {n_kept:,} usable L2 pairs")

    def _mae_at(tau, pairs):
        if not pairs:
            return None
        if tau >= 1e8:
            err_sum = sum(w * abs(e + b) for (_l, e, b, w) in pairs)
        else:
            err_sum = sum(w * abs(e + math.exp(-l / tau) * b) for (l, e, b, w) in pairs)
        w_sum = sum(w for (_l, _e, _b, w) in pairs)
        return err_sum / w_sum if w_sum > 0 else None

    tau_hours_out = {}
    heldout_out = {}
    n_train_out = {}
    n_test_out = {}

    print()
    print(f"{'field':<6}{'n_train':>10}{'n_test':>10}{'fitted τ':>14}"
          f"{'MAE_flat':>12}{'MAE_def':>12}{'MAE_fit':>12}"
          f"{'%vs_def':>10}{'%vs_flat':>10}")
    print("-" * 96)
    for f in L2_TAU_FIELDS:
        train_pairs = l2_train.get(f, [])
        test_pairs  = l2_test.get(f, [])
        n_train = len(train_pairs)
        n_test  = len(test_pairs)
        n_train_out[f] = n_train
        n_test_out[f] = n_test
        if n_train < L2_TAU_MIN_PAIRS:
            print(f"{f:<6}{n_train:>10}{n_test:>10}{'(skipped)':>14}")
            continue
        best_tau = None
        best_mae = float("inf")
        for tau in L2_TAU_GRID:
            m = _mae_at(tau, train_pairs)
            if m is None:
                continue
            if m < best_mae:
                best_mae = m
                best_tau = tau
        tau_hours_out[f] = "inf" if best_tau >= 1e8 else (
            int(best_tau) if best_tau == int(best_tau) else round(best_tau, 2))

        mae_flat = mae_default = mae_fitted = None
        imp_def = imp_flat = None
        if n_test >= max(100, L2_TAU_MIN_PAIRS // 5):
            mae_flat    = _mae_at(1e9, test_pairs)
            mae_default = _mae_at(L2_DEFAULT_TAUS.get(f, 1e9), test_pairs)
            mae_fitted  = _mae_at(best_tau, test_pairs)
            imp_def = (100.0 * (mae_default - mae_fitted) / mae_default
                       if (mae_default and mae_default > 0) else 0.0)
            imp_flat = (100.0 * (mae_flat - mae_fitted) / mae_flat
                        if (mae_flat and mae_flat > 0) else 0.0)
            heldout_out[f] = {
                "n_test": n_test,
                "mae_flat": round(mae_flat, 4) if mae_flat is not None else None,
                "mae_default": round(mae_default, 4) if mae_default is not None else None,
                "mae_fitted": round(mae_fitted, 4) if mae_fitted is not None else None,
                "improvement_vs_default_pct": round(imp_def, 2),
                "improvement_vs_flat_pct": round(imp_flat, 2),
            }

        tau_show = "∞" if best_tau >= 1e8 else f"{best_tau:g}h"
        rf  = f"{mae_flat:.3f}" if mae_flat is not None else "—"
        rd  = f"{mae_default:.3f}" if mae_default is not None else "—"
        rfit = f"{mae_fitted:.3f}" if mae_fitted is not None else "—"
        idef = f"{imp_def:+.2f}%" if imp_def is not None else "—"
        iflt = f"{imp_flat:+.2f}%" if imp_flat is not None else "—"
        print(f"{f:<6}{n_train:>10,}{n_test:>10,}{tau_show:>14}"
              f"{rf:>12}{rd:>12}{rfit:>12}{idef:>10}{iflt:>10}")

    out_doc = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs_total": n_kept,
        "retention_days": RETENTION_DAYS,
        "heldout_days": L2_HELDOUT_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "tau_hours": tau_hours_out,
        "heldout": heldout_out,
        "n_pairs_per_field": {"train": n_train_out, "test": n_test_out},
        "default_taus": dict(L2_DEFAULT_TAUS),
        "preview": True,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as fout:
        json.dump(out_doc, fout, indent=2)
    print()
    print(f"Preview written to {OUT_PATH}")
    print()
    print("Guardrail simulation (per loader's per-field rules):")
    for f in L2_TAU_FIELDS:
        if f not in L2_DEFAULT_TAUS:
            continue
        default_tau = L2_DEFAULT_TAUS[f]
        v = tau_hours_out.get(f)
        if v is None:
            print(f"  {f}: no fit → use default {default_tau}h")
            continue
        tau_val = 1e9 if v == "inf" else float(v)
        h = heldout_out.get(f, {})
        n_test = h.get("n_test", 0)
        imp = h.get("improvement_vs_default_pct")
        if imp is None or n_test < 100:
            print(f"  {f}: no held-out score (n_test={n_test}) → use default {default_tau}h")
            continue
        if imp < 0:
            print(f"  {f}: held-out {imp:+.2f}% below 0 → use default {default_tau}h")
            continue
        if tau_val < 1e8 and not (0.25 * default_tau <= tau_val <= 4.0 * default_tau):
            print(f"  {f}: τ={tau_val}h outside guardrail "
                  f"[{0.25*default_tau:.1f}, {4*default_tau:.1f}] → use default {default_tau}h")
            continue
        print(f"  {f}: ✓ ADOPT τ={tau_val}h ({imp:+.2f}% held-out vs default, n_test={n_test:,})")


if __name__ == "__main__":
    main()
