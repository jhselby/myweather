"""Orthogonality: KBOS-vs-KBVY cloud σ (C1d candidate) vs C1a (transition)
AND vs C1e (post-frontal).

Companion to h_cloud_disagreement.py — that script proved SMOKE_ALIVE
(high-σ cells have ≥1.2x MAE vs low-σ cells on at least one cloud field).
This script answers whether C1d carries independent signal vs the C1 axes
already promoted (C1a regime-transition and C1e post-frontal), or whether
it's redundant with them.

Method:
  Stream pair log; filter to cloud fields with cloud_inter_source_sigma set.
  Build a binary HIGH/LOW σ axis using the data's own Q3 threshold (same
  cut h_cloud_disagreement uses). For each row also compute:
    - C1a: state_fc.regime_synoptic ≠ state_obs.regime_synoptic
    - C1e: hours_since_front < 24h (from frontal_events_log.json)
  Aggregate |error_l4| per (field, lead_band, σ_axis, C1a, C1e) cell.
  Compare HIGH-σ / LOW-σ MAE ratio with C1a held constant and again with
  C1e held constant. ORTHOGONAL = ratio stays ≥1.20 in both subsets.

Verdicts:
  → PROMOTE if ≥4 orthogonal cells across both checks
  → KILL if ≥70% of cells are REDUNDANT
  → MIXED otherwise — narrow promote on the orthogonal cells.

Built 2026-06-29 to finish the C1d Stage 2 question.
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from statistics import median

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_URL  = "https://data.wymancove.com/forecast_error_log.jsonl"
FRONT_URL = "https://data.wymancove.com/frontal_events_log.json"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "h_cloud_disagreement_orthogonality.txt")

FIELDS = ("cc", "cl", "cm", "ch")
BANDS  = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
HSF_THRESHOLD = 24  # hours since front: post-frontal axis
MIN_N_PER_CELL = 100


def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def main():
    print("=" * 86)
    print("H_CLOUD_DISAGREEMENT_ORTHOGONALITY — C1d vs C1a (transition) and C1e (post-frontal)")
    print("=" * 86)

    # Load frontal events for hours-since-front computation
    try:
        req = urllib.request.Request(FRONT_URL, headers={"User-Agent": "curl/8.4.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            passage_dts = sorted(
                datetime.fromisoformat(e.get("ts", "").replace("Z", "")[:19])
                for e in json.loads(r.read()).get("entries", []) if e.get("ts")
            )
        print(f"\n[1/4] Loaded {len(passage_dts)} frontal passages")
    except Exception as e:
        print(f"\n[1/4] Failed to load frontal events: {e}")
        print("Cannot evaluate C1e orthogonality without frontal data. Aborting.")
        return 1

    def hsf(obs_dt):
        lo, hi = 0, len(passage_dts)
        while lo < hi:
            mid = (lo + hi) // 2
            if passage_dts[mid] <= obs_dt:
                lo = mid + 1
            else:
                hi = mid
        return (obs_dt - passage_dts[lo - 1]).total_seconds() / 3600 if lo > 0 else None

    print("\n[2/4] First pass: collect cloud_inter_source_sigma distribution for Q3 cut...")
    sigmas = []
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") not in FIELDS:
                continue
            s = r.get("cloud_inter_source_sigma")
            if s is not None:
                sigmas.append(float(s))

    if len(sigmas) < 5000:
        print(f"  Only {len(sigmas)} post-wiring rows with σ — INSUFFICIENT (need ≥5000).")
        print("  Re-run after more pair-log accumulation (~2026-07-04).")
        return 0

    s_sorted = sorted(sigmas)
    q1_sigma = s_sorted[len(s_sorted) // 4]
    q3_sigma = s_sorted[(3 * len(s_sorted)) // 4]
    print(f"  n={len(sigmas):,}, σ Q1≤{q1_sigma:.2f}, median={median(s_sorted):.2f}, "
          f"Q3≥{q3_sigma:.2f}")
    print(f"  Binary HIGH = σ ≥ Q3 ({q3_sigma:.2f}), LOW = σ ≤ Q1 ({q1_sigma:.2f})")

    print("\n[3/4] Second pass: aggregate by (field, band, σ_HIGH, C1a, C1e)...")
    # (field, band, sigma_HIGH, C1a, C1e) -> [n, sum|err|]
    sums = defaultdict(lambda: [0, 0.0])

    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in FIELDS:
                continue
            sigma = r.get("cloud_inter_source_sigma")
            if sigma is None:
                continue
            sigma = float(sigma)
            # Drop middle quartiles — clean HIGH vs LOW comparison only
            if q1_sigma < sigma < q3_sigma:
                continue
            sigma_HIGH = sigma >= q3_sigma

            lead_h = r.get("lead_h")
            band = lead_band(int(lead_h)) if lead_h is not None else None
            if band is None:
                continue
            err = r.get("error_l4")
            if err is None:
                err = r.get("error_l1")
            if err is None:
                continue

            sf = (r.get("state_fc") or {}).get("regime_synoptic")
            so = (r.get("state_obs") or {}).get("regime_synoptic")
            if not sf or not so:
                continue
            C1a = (sf != so)

            obs_time = r.get("obs_time", "")
            try:
                odt = datetime.fromisoformat(obs_time[:19])
            except Exception:
                continue
            s_hsf = hsf(odt)
            if s_hsf is None:
                continue
            C1e = s_hsf < HSF_THRESHOLD

            cell = sums[(f, band, sigma_HIGH, C1a, C1e)]
            cell[0] += 1
            cell[1] += abs(float(err))

    print(f"  Aggregated into {len(sums)} cells")

    def get(f, band, sigma_HIGH, C1a, C1e):
        n, s = sums.get((f, band, sigma_HIGH, C1a, C1e), (0, 0.0))
        return n, (s / n if n else 0.0)

    print("\n[4/4] Orthogonality verdicts:")

    lines = []

    def emit(s):
        print(s)
        lines.append(s)

    # vs C1a — hold C1a fixed, vary sigma
    emit("\n" + "-" * 86)
    emit("σ (C1d) × C1a (transition) — holding C1e=False (no recent front)")
    emit("-" * 86)
    emit(f"  {'field':<5} {'band':<8} {'σH/σL (no-trans)':>18} {'σH/σL (trans)':>15}  vs_C1a")
    v_c1a = defaultdict(int)
    for f in FIELDS:
        for band_label, _, _ in BANDS:
            n_hH, m_hH = get(f, band_label, True,  False, False)
            n_hL, m_hL = get(f, band_label, False, False, False)
            n_tH, m_tH = get(f, band_label, True,  True,  False)
            n_tL, m_tL = get(f, band_label, False, True,  False)
            if min(n_hH, n_hL, n_tH, n_tL) < MIN_N_PER_CELL:
                continue
            r_no_trans = m_hH / m_hL if m_hL > 0 else 0
            r_trans    = m_tH / m_tL if m_tL > 0 else 0
            if r_no_trans >= 1.20 and r_trans >= 1.20:
                verdict = "ORTHOGONAL"
            elif r_no_trans <= 1.05:
                verdict = "REDUNDANT"
            elif r_trans >= 1.20:
                verdict = "CONFOUNDED"
            else:
                verdict = "AMBIGUOUS"
            v_c1a[verdict] += 1
            emit(f"  {f:<5} {band_label:<8} {r_no_trans:>17.2f}× {r_trans:>14.2f}×  {verdict}")
    emit(f"\n  vs C1a totals: ORTHOGONAL: {v_c1a['ORTHOGONAL']}, REDUNDANT: {v_c1a['REDUNDANT']}, "
         f"CONFOUNDED: {v_c1a['CONFOUNDED']}, AMBIGUOUS: {v_c1a['AMBIGUOUS']}")

    # vs C1e — hold C1a fixed, vary C1e
    emit("\n" + "-" * 86)
    emit("σ (C1d) × C1e (post-frontal hsf<24h) — holding C1a=False (no transition)")
    emit("-" * 86)
    emit(f"  {'field':<5} {'band':<8} {'σH/σL (no-front)':>18} {'σH/σL (post-front)':>20}  vs_C1e")
    v_c1e = defaultdict(int)
    for f in FIELDS:
        for band_label, _, _ in BANDS:
            n_nH, m_nH = get(f, band_label, True,  False, False)
            n_nL, m_nL = get(f, band_label, False, False, False)
            n_pH, m_pH = get(f, band_label, True,  False, True)
            n_pL, m_pL = get(f, band_label, False, False, True)
            if min(n_nH, n_nL, n_pH, n_pL) < MIN_N_PER_CELL:
                continue
            r_no_front  = m_nH / m_nL if m_nL > 0 else 0
            r_post_front = m_pH / m_pL if m_pL > 0 else 0
            if r_no_front >= 1.20 and r_post_front >= 1.20:
                verdict = "ORTHOGONAL"
            elif r_no_front <= 1.05:
                verdict = "REDUNDANT"
            elif r_post_front >= 1.20:
                verdict = "CONFOUNDED"
            else:
                verdict = "AMBIGUOUS"
            v_c1e[verdict] += 1
            emit(f"  {f:<5} {band_label:<8} {r_no_front:>17.2f}× {r_post_front:>19.2f}×  {verdict}")
    emit(f"\n  vs C1e totals: ORTHOGONAL: {v_c1e['ORTHOGONAL']}, REDUNDANT: {v_c1e['REDUNDANT']}, "
         f"CONFOUNDED: {v_c1e['CONFOUNDED']}, AMBIGUOUS: {v_c1e['AMBIGUOUS']}")

    # Final verdict
    emit("\n" + "=" * 86)
    total_cells = sum(v_c1a.values()) + sum(v_c1e.values())
    ortho = v_c1a['ORTHOGONAL'] + v_c1e['ORTHOGONAL']
    redundant = v_c1a['REDUNDANT'] + v_c1e['REDUNDANT']
    if total_cells < 4:
        emit(f"→ INSUFFICIENT: only {total_cells} cells cleared the n≥{MIN_N_PER_CELL} floor.")
        emit("  Re-run after more pair-log accumulation.")
    elif ortho >= 4:
        emit(f"→ PROMOTE C1d: KBOS-vs-KBVY σ is independent of both C1a and C1e "
             f"({ortho} orthogonal cells / {total_cells} total).")
    elif redundant >= 0.7 * total_cells:
        emit(f"→ KILL C1d: signal captured by C1a/C1e ({redundant}/{total_cells} redundant).")
    else:
        emit(f"→ MIXED: {ortho} orthogonal / {redundant} redundant / "
             f"{total_cells - ortho - redundant} other. Narrow promote on the orthogonal cells.")
    emit("=" * 86)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
