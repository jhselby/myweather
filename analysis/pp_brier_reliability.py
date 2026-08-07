"""
pp (precipitation probability) Brier reliability decomposition.

Fills the measurement gap flagged on debug page line 1347:
  "pp Brier reliability decomposition — does '30% chance' actually happen
   30% of the time? Aggregate Brier only, no decomposition."

Bins pp forecasts by predicted-probability decile (0-10%, 10-20%, ...
90-100%) and reports empirical frequency per bin — the classical
reliability diagram. Also decomposes Brier per Murphy (1973):

    Brier = Reliability + Uncertainty − Resolution

  - Uncertainty = obs_mean × (1 − obs_mean)   [irreducible baseline]
  - Reliability = Σ nk/N × (pk − ok)^2         [calibration; lower better]
  - Resolution  = Σ nk/N × (ok − obs_mean)^2   [discrimination; higher better]

  where pk = mean predicted prob in bin k, ok = observed frequency in bin k.

Skill-score = 1 − Brier / Uncertainty. Positive = better than climatology.

Run per lead band + per production layer (raw L1 vs live Production) so
we can see whether Lc/decay chain is helping calibration or just moving
Brier around.

Run:
    python3 analysis/pp_brier_reliability.py

Output:
    analysis/output/pp_brier_reliability.txt
    analysis/output/pp_brier_reliability.json
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _output import out as _out  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = _out("pp_brier_reliability.txt")
OUT_JSON = _out("pp_brier_reliability.json")

FIELD = "pp"
BIN_EDGES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100.0001]  # last bin catches 100 inclusive
BIN_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50",
              "50-60", "60-70", "70-80", "80-90", "90-100"]

LEAD_BANDS = [("0-5", 0, 5), ("6-11", 6, 11), ("12-23", 12, 23), ("24-47", 24, 47)]

MIN_N_PER_BIN = 30  # bins below this render but don't count in decomp weighting


def lead_band(lead_h):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead_h <= hi:
            return name
    return None


def bin_of(p):
    for i in range(len(BIN_EDGES) - 1):
        if BIN_EDGES[i] <= p < BIN_EDGES[i + 1]:
            return i
    return None


def load_rows():
    rows = []
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            ob = r.get("observed")
            fc_prod = r.get("forecast")
            fc_l1 = r.get("forecast_l1")
            lead = r.get("lead_h")
            if ob is None or fc_prod is None or lead is None:
                continue
            band = lead_band(int(lead))
            if band is None:
                continue
            fc_l4 = r.get("forecast_l4")
            row = {
                "band": band,
                "obs": float(ob) / 100.0,       # convert 0/100 → 0/1
                "fc_prod": float(fc_prod) / 100.0,
                "fc_l1": float(fc_l1) / 100.0 if fc_l1 is not None else None,
                "fc_l4": float(fc_l4) / 100.0 if fc_l4 is not None else None,
            }
            rows.append(row)
    return rows


def compute_reliability(rows, key):
    """Return per-bin table + Murphy decomposition for the given fc key.
    Returns (bins_list, decomp_dict) or (None, None) if not enough data."""
    bins = defaultdict(lambda: {"sum_p": 0.0, "sum_o": 0.0, "n": 0})
    n_total = 0
    sum_obs = 0.0
    sum_brier = 0.0
    for r in rows:
        p = r.get(key)
        if p is None:
            continue
        b = bin_of(p * 100.0)
        if b is None:
            continue
        bins[b]["sum_p"] += p
        bins[b]["sum_o"] += r["obs"]
        bins[b]["n"] += 1
        n_total += 1
        sum_obs += r["obs"]
        sum_brier += (p - r["obs"]) ** 2
    if n_total == 0:
        return None, None

    obs_mean = sum_obs / n_total
    uncertainty = obs_mean * (1.0 - obs_mean)
    brier = sum_brier / n_total

    reliability = 0.0
    resolution = 0.0
    bins_list = []
    for b in range(len(BIN_LABELS)):
        entry = bins.get(b)
        if not entry or entry["n"] == 0:
            bins_list.append({
                "bin": BIN_LABELS[b], "n": 0,
                "predicted": None, "observed": None, "gap": None,
            })
            continue
        p_mean = entry["sum_p"] / entry["n"]
        o_mean = entry["sum_o"] / entry["n"]
        w = entry["n"] / n_total
        reliability += w * (p_mean - o_mean) ** 2
        resolution += w * (o_mean - obs_mean) ** 2
        bins_list.append({
            "bin": BIN_LABELS[b],
            "n": entry["n"],
            "predicted": round(p_mean * 100, 2),
            "observed": round(o_mean * 100, 2),
            "gap": round((p_mean - o_mean) * 100, 2),
        })
    skill = 1.0 - brier / uncertainty if uncertainty > 0 else 0.0
    decomp = {
        "n": n_total,
        "obs_freq_pct": round(obs_mean * 100, 3),
        "brier": round(brier, 5),
        "reliability": round(reliability, 5),
        "resolution": round(resolution, 5),
        "uncertainty": round(uncertainty, 5),
        "skill_vs_climatology": round(skill, 4),
        # sanity: Brier ≈ Reliability + Uncertainty − Resolution
        "sanity_residual": round(brier - (reliability + uncertainty - resolution), 6),
    }
    return bins_list, decomp


def main():
    rows = load_rows()
    if not rows:
        print(f"No {FIELD} rows in pair log; aborting.", file=sys.stderr)
        return 1

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit("pp BRIER RELIABILITY DECOMPOSITION")
    emit("=" * 100)
    emit(f"Total pp rows: {len(rows):,}")
    emit("Brier = Reliability + Uncertainty − Resolution  (Murphy 1973)")
    emit("  Reliability: calibration gap (lower better); Resolution: discrimination (higher better);")
    emit("  Uncertainty: irreducible baseline = p_base × (1−p_base).")
    emit("Skill vs climatology = 1 − Brier/Uncertainty. Positive = beats always-guess-base-rate.")
    emit("")

    # Overall (pooled all bands) — raw L1 vs L4 (post-decay) vs Production (live)
    # Note: pp's top-level `forecast` field may carry L1 semantics per
    # [[feedback_measure_against_live_stack_baseline]]. L4 is the deepest
    # numbered layer for pp; if fc_l4 differs from fc_prod, "Production" is
    # under-reporting the live-stack improvement.
    payload = {"overall": {}, "by_band": {}, "generated_at": None}
    for key, lbl in (("fc_l1", "L1 (raw)"), ("fc_l4", "L4 (post-decay)"), ("fc_prod", "Production")):
        bins_list, decomp = compute_reliability(rows, key)
        if decomp is None:
            continue
        payload["overall"][lbl] = {"bins": bins_list, "decomp": decomp}
        emit("-" * 100)
        emit(f"[OVERALL — {lbl}] n={decomp['n']:,}  obs_freq={decomp['obs_freq_pct']}%  "
             f"Brier={decomp['brier']}  skill={decomp['skill_vs_climatology']:+.4f}")
        emit(f"           Reliability={decomp['reliability']}  "
             f"Resolution={decomp['resolution']}  Uncertainty={decomp['uncertainty']}")
        emit("-" * 100)
        emit(f"{'bin':>7} {'n':>6}  {'pred %':>8}  {'obs %':>8}  {'gap':>7}   {'reliability':>12}")
        for b in bins_list:
            if b["n"] == 0:
                emit(f"{b['bin']:>7} {b['n']:>6}  {'—':>8}  {'—':>8}  {'—':>7}")
            else:
                mark = " ★" if abs(b["gap"]) < 5 else ("  ⚠" if abs(b["gap"]) > 15 else "")
                emit(f"{b['bin']:>7} {b['n']:>6}  {b['predicted']:>8.2f}  "
                     f"{b['observed']:>8.2f}  {b['gap']:>+7.2f}{mark}")
        emit("")

    # Per lead-band, Production only (most decision-relevant)
    for band_name, lo, hi in LEAD_BANDS:
        band_rows = [r for r in rows if r["band"] == band_name]
        if not band_rows:
            continue
        bins_list, decomp = compute_reliability(band_rows, "fc_prod")
        if decomp is None:
            continue
        payload["by_band"][band_name] = {"bins": bins_list, "decomp": decomp}
        emit("-" * 100)
        emit(f"[LEAD {band_name}h — Production] n={decomp['n']:,}  "
             f"obs_freq={decomp['obs_freq_pct']}%  Brier={decomp['brier']}  "
             f"skill={decomp['skill_vs_climatology']:+.4f}")
        emit(f"           Reliability={decomp['reliability']}  "
             f"Resolution={decomp['resolution']}")
        emit("-" * 100)
        emit(f"{'bin':>7} {'n':>6}  {'pred %':>8}  {'obs %':>8}  {'gap':>7}")
        for b in bins_list:
            if b["n"] == 0:
                emit(f"{b['bin']:>7} {b['n']:>6}  {'—':>8}  {'—':>8}  {'—':>7}")
            else:
                mark = " ★" if abs(b["gap"]) < 5 else ("  ⚠" if abs(b["gap"]) > 15 else "")
                emit(f"{b['bin']:>7} {b['n']:>6}  {b['predicted']:>8.2f}  "
                     f"{b['observed']:>8.2f}  {b['gap']:>+7.2f}{mark}")
        emit("")

    # Verdict — Production is the live-scored series (pp L3 dropped 07-04,
    # so Production == L1 by design in the current pair log; that's expected,
    # not a bug — see [[project_pp_brier_reliability]] retraction).
    emit("=" * 100)
    l1 = payload["overall"].get("L1 (raw)", {}).get("decomp") or {}
    prod = payload["overall"].get("Production", {}).get("decomp") or {}

    # Calibration bias — is raw HRRR pp systematically under- or over-forecasting?
    # This is the surviving signal from the 07-21 investigation: the Stage 0
    # candidate is a bin-weighted probability lift table applied to raw fc.
    raw_bins = payload["overall"].get("L1 (raw)", {}).get("bins") or []
    signed_bias_pts = []
    for b in raw_bins:
        if b["n"] >= MIN_N_PER_BIN and b["gap"] is not None:
            signed_bias_pts.append(b["gap"] * b["n"])
    total_weighted_n = sum(b["n"] for b in raw_bins if b["n"] >= MIN_N_PER_BIN)
    verdict_payload = {}
    if total_weighted_n > 0:
        weighted_bias = sum(signed_bias_pts) / total_weighted_n
        # Largest gap in a well-populated bin — the candidate's biggest-lift cell.
        eligible = [b for b in raw_bins if b["n"] >= MIN_N_PER_BIN and b["gap"] is not None]
        worst = max(eligible, key=lambda b: abs(b["gap"])) if eligible else None
        direction = "UNDER" if weighted_bias < -2 else ("OVER" if weighted_bias > 2 else "CAL")
        emit(f"Calibration bias (raw HRRR, weighted by bin n): {weighted_bias:+.2f}pp — "
             f"raw pp is {'under-' if direction == 'UNDER' else 'over-' if direction == 'OVER' else 'well-'}"
             f"forecasting wet outcomes.")
        if worst:
            emit(f"Largest gap: bin {worst['bin']} predicted {worst['predicted']}% → "
                 f"observed {worst['observed']}% (gap {worst['gap']:+.1f}pp, n={worst['n']:,}).")
        emit("")
        # Promotion-track verdict — routes to executive summary + digest verdict-grep.
        # Trigger on EITHER a large weighted bias OR a large gap in a well-populated
        # bin. The 0-10 bin holds ~80% of pp rows and is near-perfectly calibrated,
        # so it drags the weighted mean toward zero even when a mid-range bin
        # (e.g. 30-40 with a −28pp gap on n=1,422) is unambiguously mis-calibrated.
        big_bin_gap = worst and worst["n"] >= 500 and abs(worst["gap"]) >= 15
        if (direction in ("UNDER", "OVER") and abs(weighted_bias) >= 5) or big_bin_gap:
            emit(f"→ STAGE0 CANDIDATE OPEN: pp bin-lift calibration table.")
            emit(f"VERDICT: STAGE0_OPEN pp_bin_lift_calibration weighted_bias={weighted_bias:+.2f}pp "
                 f"worst_bin={worst['bin'] if worst else 'n/a'} worst_gap={worst['gap']:+.1f}pp "
                 f"(halves-test via h_pp_bin_calibration.py to promote → Stage 1).")
            verdict_payload = {
                "state": "STAGE0_OPEN",
                "candidate": "pp_bin_lift_calibration",
                "weighted_bias_pp": round(weighted_bias, 2),
                "worst_bin": worst["bin"] if worst else None,
                "worst_bin_predicted_pct": worst["predicted"] if worst else None,
                "worst_bin_observed_pct": worst["observed"] if worst else None,
                "worst_bin_gap_pp": worst["gap"] if worst else None,
                "worst_bin_n": worst["n"] if worst else None,
                "next_step": "h_pp_bin_calibration.py halves-test",
            }
        else:
            emit(f"→ CLEAN: raw pp is well-calibrated; no Stage 0 candidate.")
            emit(f"VERDICT: CLEAN pp_bin_lift_calibration weighted_bias={weighted_bias:+.2f}pp")
            verdict_payload = {
                "state": "CLEAN",
                "candidate": "pp_bin_lift_calibration",
                "weighted_bias_pp": round(weighted_bias, 2),
            }
    emit("=" * 100)
    payload["verdict"] = verdict_payload

    # Finalize
    from datetime import datetime, timezone
    payload["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["source"] = f"forecast_error_log.jsonl (field={FIELD})"
    payload["bin_edges"] = BIN_EDGES[:-1] + [100]  # cosmetic — last edge is 100 not 100.0001

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)
    # Publish to GCS so the debug page can fetch via
    # https://data.wymancove.com/pp_brier_reliability.json. Silent no-op
    # on any failure — local artifact still lands.
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "pp_brier_reliability.json", "pp_brier_reliability.json")
        print("  ✓ Published to gs://myweather-data/pp_brier_reliability.json", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
