"""
pp Brier decomposition — reliability / resolution / uncertainty for POP.

Phase 3 of the measurement-framework roadmap. We already have aggregate
Brier via pop_calibration.py; this splits it into the three canonical
components so we can tell WHY Brier is where it is:

  Brier = Reliability − Resolution + Uncertainty

  Reliability  = Σ_k (n_k / N) × (fc_k − obs_k)²
                 → 0 = perfect calibration ("30% means 30% of the time")
  Resolution   = Σ_k (n_k / N) × (obs_k − obs_bar)²
                 → 0 = forecast has no discrimination; higher = more skill
  Uncertainty  = obs_bar × (1 − obs_bar)
                 → intrinsic climatological variance; forecaster can't reduce

The pair log records pp as forecast probability (0-100 scale) and observed
as 0/100 binary (100 if the hour had any precip, else 0). We convert to
[0, 1] probabilities and bin the forecast by probability decile.

Two forecast stages compared:
  raw       = forecast_l1   (pre-decay HRRR/GFS blend)
  corrected = forecast      (post-Fitter — what user sees)

Emits per-band decomposition and pooled. Verdict summarizes whether
Reliability improved or worsened from raw → corrected (the calibrator's
whole point).

Run:
    python3 analysis/pp_brier_decomposition.py

Output:
    analysis/output/pp_brier_decomposition.txt
    analysis/output/pp_brier_decomposition.json
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "pp_brier_decomposition.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "pp_brier_decomposition.json")

# Decile bins over probability. Fine at the low end where most rows sit.
BIN_EDGES = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0001]

# Lead bands (hours) — same as h_persistence_skill etc.
BANDS = [
    ("0-5h",   0, 5),
    ("6-11h",  6, 11),
    ("12-23h", 12, 23),
    ("24-47h", 24, 47),
]

MIN_N_PER_BAND = 500


def _bin_of(p):
    for i in range(len(BIN_EDGES) - 1):
        if BIN_EDGES[i] <= p < BIN_EDGES[i + 1]:
            return i
    return len(BIN_EDGES) - 2


def _decompose(pairs):
    """pairs: list of (fc_prob, obs_binary) in [0,1] / {0,1}.
    Returns dict with brier, reliability, resolution, uncertainty, obs_bar, bins."""
    n_total = len(pairs)
    if n_total == 0:
        return None
    obs_sum = sum(o for _, o in pairs)
    obs_bar = obs_sum / n_total
    uncertainty = obs_bar * (1 - obs_bar)

    bins = defaultdict(list)
    for fc, ob in pairs:
        bins[_bin_of(fc)].append((fc, ob))

    reliability = 0.0
    resolution = 0.0
    brier = 0.0
    bin_out = []
    for i in range(len(BIN_EDGES) - 1):
        b = bins.get(i, [])
        n_k = len(b)
        if n_k == 0:
            continue
        fc_k = sum(fc for fc, _ in b) / n_k
        obs_k = sum(o for _, o in b) / n_k
        weight = n_k / n_total
        reliability += weight * (fc_k - obs_k) ** 2
        resolution  += weight * (obs_k - obs_bar) ** 2
        bin_out.append({
            "bin": f"{BIN_EDGES[i]:.2f}-{BIN_EDGES[i+1]:.2f}",
            "n": n_k,
            "fc_mean": round(fc_k, 4),
            "obs_freq": round(obs_k, 4),
            "gap": round(fc_k - obs_k, 4),
        })
    # Aggregate Brier from pair-level for a decomposition sanity check.
    for fc, ob in pairs:
        brier += (fc - ob) ** 2
    brier /= n_total
    # Decomp identity: Brier = Reliability − Resolution + Uncertainty.
    decomp_check = reliability - resolution + uncertainty
    return {
        "n": n_total,
        "obs_bar": round(obs_bar, 4),
        "brier": round(brier, 5),
        "reliability": round(reliability, 5),
        "resolution": round(resolution, 5),
        "uncertainty": round(uncertainty, 5),
        "decomp_check": round(decomp_check, 5),
        "decomp_gap": round(brier - decomp_check, 5),  # should be ~0 if math is right
        "brier_skill_vs_climatology": round(1 - brier / uncertainty, 4) if uncertainty > 0 else None,
        "bins": bin_out,
    }


def compute():
    """Stream pair log; bucket pp pairs by band + by stage."""
    raw_pairs_by_band = defaultdict(list)   # forecast_l1
    corr_pairs_by_band = defaultdict(list)  # forecast (post-Fitter)
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "pp":
                continue
            obs = r.get("observed")
            fc_corr = r.get("forecast")
            fc_l1 = r.get("forecast_l1")
            if obs is None or fc_corr is None:
                continue
            lead = r.get("lead_h")
            if lead is None:
                continue
            band = None
            for name, lo, hi in BANDS:
                if lo <= lead <= hi:
                    band = name
                    break
            if band is None:
                continue
            obs_p = 1.0 if float(obs) > 0 else 0.0
            fc_corr_p = max(0.0, min(1.0, float(fc_corr) / 100.0))
            corr_pairs_by_band[band].append((fc_corr_p, obs_p))
            if fc_l1 is not None:
                fc_l1_p = max(0.0, min(1.0, float(fc_l1) / 100.0))
                raw_pairs_by_band[band].append((fc_l1_p, obs_p))
    return raw_pairs_by_band, corr_pairs_by_band


def emit(raw_by_band, corr_by_band):
    lines = []
    lines.append("=" * 100)
    lines.append("pp BRIER DECOMPOSITION — Reliability / Resolution / Uncertainty per lead band")
    lines.append("=" * 100)
    lines.append("Brier = Reliability − Resolution + Uncertainty  (lower Brier = better)")
    lines.append("Reliability → 0 = perfectly calibrated.  Resolution → higher = more discrimination.")
    lines.append("Uncertainty = obs_bar(1 − obs_bar), fixed by the weather.")
    lines.append("BSS_vs_climo = 1 − Brier / Uncertainty. Positive = better than always-forecasting-mean.")
    lines.append("")

    hdr = f"{'stage':<10}{'band':<8}{'n':>9}{'obs_bar':>10}{'Brier':>10}{'Reli':>9}{'Reso':>9}{'Unc':>9}{'BSS':>9}"
    lines.append(hdr)
    lines.append("-" * len(hdr))

    per_stage_band = {}
    for band_name, _, _ in BANDS:
        for stage, source in (("raw", raw_by_band), ("corrected", corr_by_band)):
            pairs = source.get(band_name, [])
            if len(pairs) < MIN_N_PER_BAND:
                lines.append(f"{stage:<10}{band_name:<8}{len(pairs):>9,}  (thin — need ≥{MIN_N_PER_BAND})")
                continue
            d = _decompose(pairs)
            per_stage_band[(stage, band_name)] = d
            bss = d["brier_skill_vs_climatology"]
            bss_txt = f"{bss:+.3f}" if bss is not None else "  --"
            lines.append(
                f"{stage:<10}{band_name:<8}{d['n']:>9,}{d['obs_bar']:>10.4f}"
                f"{d['brier']:>10.5f}{d['reliability']:>9.5f}{d['resolution']:>9.5f}"
                f"{d['uncertainty']:>9.5f}{bss_txt:>9}"
            )
        lines.append("")

    # Pooled
    lines.append("=" * 100)
    lines.append("POOLED (all leads) — headline")
    lines.append("=" * 100)
    for stage, source in (("raw", raw_by_band), ("corrected", corr_by_band)):
        all_pairs = []
        for band_name, _, _ in BANDS:
            all_pairs.extend(source.get(band_name, []))
        d = _decompose(all_pairs) if all_pairs else None
        if d is None:
            continue
        per_stage_band[(stage, "pooled")] = d
        bss = d["brier_skill_vs_climatology"]
        bss_txt = f"{bss:+.3f}" if bss is not None else "  --"
        lines.append(
            f"{stage:<10}{'pooled':<8}{d['n']:>9,}{d['obs_bar']:>10.4f}"
            f"{d['brier']:>10.5f}{d['reliability']:>9.5f}{d['resolution']:>9.5f}"
            f"{d['uncertainty']:>9.5f}{bss_txt:>9}"
        )
    lines.append("")

    # Per-bin gap dump for the pooled corrected stage — this is the calibration diagnostic
    d_corr = per_stage_band.get(("corrected", "pooled"))
    if d_corr:
        lines.append("Per-bin calibration (pooled corrected) — gap = fc_mean − obs_freq")
        lines.append(f"{'bin':<12}{'n':>9}{'fc_mean':>10}{'obs_freq':>10}{'gap':>10}")
        for b in d_corr["bins"]:
            mark = " ★" if abs(b["gap"]) > 0.10 else ("  ⚠" if abs(b["gap"]) > 0.05 else "  ")
            lines.append(
                f"{b['bin']:<12}{b['n']:>9,}{b['fc_mean']:>10.4f}"
                f"{b['obs_freq']:>10.4f}{b['gap']:>+10.4f}{mark}"
            )
        lines.append("")

    # Verdict — did the calibrator improve reliability, and by how much?
    raw_pool = per_stage_band.get(("raw", "pooled"))
    cor_pool = per_stage_band.get(("corrected", "pooled"))
    if raw_pool and cor_pool:
        d_reli = cor_pool["reliability"] - raw_pool["reliability"]
        d_reso = cor_pool["resolution"] - raw_pool["resolution"]
        d_brier = cor_pool["brier"] - raw_pool["brier"]
        reli_pct = -d_reli / raw_pool["reliability"] * 100 if raw_pool["reliability"] > 0 else 0.0
        # Reliability improvement + Resolution kept ≥ raw → calibrator working
        if d_reli < 0 and d_reso >= -1e-4:
            verdict = (f"Verdict: CALIBRATED — corrected Reliability {reli_pct:+.1f}% better than raw "
                       f"(Δ Brier {d_brier:+.5f}; Δ Resolution {d_reso:+.5f}).")
        elif d_reli < 0 and d_reso < -1e-4:
            verdict = (f"Verdict: MIXED — Reliability {reli_pct:+.1f}% better, but Resolution dropped "
                       f"({d_reso:+.5f}). Calibrator is over-shrinking toward the base rate.")
        else:
            verdict = (f"Verdict: NOT CALIBRATED — corrected Reliability worse than raw "
                       f"({-reli_pct:+.1f}%). Investigate.")
        lines.append(verdict)
    else:
        lines.append("Verdict: THIN — insufficient pooled data.")

    return "\n".join(lines), per_stage_band


def main():
    raw_by_band, corr_by_band = compute()
    text, per_stage_band = emit(raw_by_band, corr_by_band)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "forecast_error_log.jsonl (field=pp)",
        "definitions": {
            "brier": "mean squared error of forecast probability vs binary obs",
            "reliability": "Σ n_k/N × (fc_k − obs_k)² — lower is better calibration",
            "resolution": "Σ n_k/N × (obs_k − obs_bar)² — higher = more discrimination",
            "uncertainty": "obs_bar × (1 − obs_bar), climatological variance",
            "brier_skill_vs_climatology": "1 − brier/uncertainty",
        },
        "bin_edges": BIN_EDGES,
        "results": {f"{s}/{b}": v for (s, b), v in per_stage_band.items()},
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
