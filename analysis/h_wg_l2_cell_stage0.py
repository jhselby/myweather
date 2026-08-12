"""Stage 0 — does wg L2 (wind_blend) hurt per (regime × lead_band) cell?

Motivated by [[project_wg_l2_windblend_cell_concern]] (2026-08-12): in wg
L3-SKIP cells (calm/sea_breeze mid-to-long lead) the top-of-stack (L2,
since L3 is skipped) is worse than raw L1 by +8-23%. Since L3 doesn't
fire in those cells, that damage is on L2. Question: does the L1-vs-L2
comparison hold cell-by-cell on halves-verified numbers?

Method mirrors h_wg_l3_regression_stage1.py but compares L1 (raw) vs L2
(wind_blend output) instead of L2 vs L3. Cell is a candidate for an
L2 SKIP entry if L2 hurts stably on both halves + full window.

Verdict per cell (n >= MIN_N):
  L2 SKIP    — L2 loses to raw by >= HURT_FLOOR on BOTH halves AND full
  MARGIN     — full loses but one half is < floor
  KEEP       — L2 helps on full OR halves disagree in sign
  THIN       — n < MIN_N in any window

Ships an analysis text; does NOT emit a curated JSON — that's a Stage 1
concern once cells are confirmed.
"""
import os
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_wg_l2_cell_stage0.txt")

WIN_A_LO, WIN_A_HI, WIN_B_LO, WIN_B_HI, WIN_FULL_LO, WIN_FULL_HI = rolling_windows()

FIELD = "wg"
MIN_N_CELL = 200
HURT_FLOOR_PCT = 3.0

# Cells the 08-12 memory flagged from top-of-stack-vs-raw. If L1-vs-L2
# reproduces the hurt on these, they're candidates for wg L2 SKIP.
FOCUS_CELLS = {
    ("calm",       "12-23"),
    ("calm",       "24-47"),
    ("sea_breeze", "6-11"),
    ("sea_breeze", "24-47"),
}

LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def lead_band(lead):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead <= hi:
            return name
    return None


def compute():
    path = cached_path(URL)
    accum = defaultdict(lambda: {"n": 0, "ae_l1": 0.0, "ae_l2": 0.0,
                                  "n_l2_missing": 0})
    n_rows = 0

    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            rt = r.get("run_time", "")
            if WIN_A_LO <= rt < WIN_A_HI:
                windows = ["A", "FULL"]
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = ["B", "FULL"]
            else:
                continue

            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            band = lead_band(lead)
            if band is None:
                continue

            ob = r.get("observed")
            fc_l1 = r.get("forecast_l1") or r.get("forecast")
            fc_l2 = r.get("forecast_l2")
            if ob is None or fc_l1 is None:
                continue

            regime = (r.get("state_fc") or {}).get("regime_synoptic") or "unknown"
            ob_f = float(ob)
            err_l1 = float(fc_l1) - ob_f

            n_rows += 1
            for win in windows:
                a = accum[(win, regime, band)]
                a["n"] += 1
                a["ae_l1"] += abs(err_l1)
                if fc_l2 is None:
                    a["n_l2_missing"] += 1
                    continue
                a["ae_l2"] += abs(float(fc_l2) - ob_f)

    print(f"scored {n_rows:,} wg rows", file=sys.stderr)
    return accum


def mae(bkt, key):
    n = bkt["n"] - (bkt["n_l2_missing"] if key == "ae_l2" else 0)
    return (bkt[key] / n) if n else None


def cell_verdict(m_l1_f, m_l2_f, m_l1_a, m_l2_a, m_l1_b, m_l2_b,
                 n_full, n_l2_missing_full):
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    if (m_l1_f is None or m_l2_f is None or
        m_l1_a is None or m_l2_a is None or
        m_l1_b is None or m_l2_b is None):
        return "THIN", None, None, None
    d_full = 100.0 * (m_l2_f - m_l1_f) / m_l1_f
    d_a = 100.0 * (m_l2_a - m_l1_a) / m_l1_a
    d_b = 100.0 * (m_l2_b - m_l1_b) / m_l1_b
    if (d_full >= HURT_FLOOR_PCT and d_a >= HURT_FLOOR_PCT
        and d_b >= HURT_FLOOR_PCT):
        return "L2 SKIP", d_full, d_a, d_b
    if d_full >= HURT_FLOOR_PCT:
        return "MARGIN", d_full, d_a, d_b
    return "KEEP", d_full, d_a, d_b


def main():
    accum = compute()

    all_cells = set()
    for (_win, regime, band) in accum.keys():
        all_cells.add((regime, band))

    lines = []
    lines.append("=" * 108)
    lines.append("wg L2 (wind_blend) per-cell — L1 (raw) vs L2 (blend), halves-verified")
    lines.append("=" * 108)
    lines.append(f"Windows: A={WIN_A_LO[:10]} → {WIN_A_HI[:10]}   "
                 f"B={WIN_B_LO[:10]} → {WIN_B_HI[:10]}   "
                 f"FULL={WIN_FULL_LO[:10]} → {WIN_FULL_HI[:10]}")
    lines.append(f"Per-cell L2 SKIP verdict: halves-stability + full >= +{HURT_FLOOR_PCT}% "
                 f"(L2 worse than raw L1).  MIN_N={MIN_N_CELL}.")
    lines.append("")
    lines.append(f"{'regime':<14}{'band':<8}{'n_full':>8}{'L1_full':>10}{'L2_full':>10}"
                 f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict  focus?")
    lines.append("-" * 108)

    focus_hits = []
    skip_candidates = []
    for (regime, band) in sorted(all_cells):
        f = accum.get(("FULL", regime, band), {"n": 0, "ae_l1": 0.0, "ae_l2": 0.0, "n_l2_missing": 0})
        a = accum.get(("A", regime, band), {"n": 0, "ae_l1": 0.0, "ae_l2": 0.0, "n_l2_missing": 0})
        b = accum.get(("B", regime, band), {"n": 0, "ae_l1": 0.0, "ae_l2": 0.0, "n_l2_missing": 0})
        m_l1_f, m_l2_f = mae(f, "ae_l1"), mae(f, "ae_l2")
        m_l1_a, m_l2_a = mae(a, "ae_l1"), mae(a, "ae_l2")
        m_l1_b, m_l2_b = mae(b, "ae_l1"), mae(b, "ae_l2")

        verdict, d_full, d_a, d_b = cell_verdict(
            m_l1_f, m_l2_f, m_l1_a, m_l2_a, m_l1_b, m_l2_b,
            f["n"], f["n_l2_missing"]
        )
        is_focus = (regime, band) in FOCUS_CELLS
        focus_mark = "★" if is_focus else ""

        def fmt(v, w=8, prec=2):
            if v is None: return f"{'—':>{w}}"
            return f"{v:>{w}.{prec}f}"

        lines.append(f"{regime:<14}{band:<8}{f['n']:>8,}"
                     f"{fmt(m_l1_f, 10, 3)}{fmt(m_l2_f, 10, 3)}"
                     f"{fmt(d_full, 10)}{fmt(d_a, 9)}{fmt(d_b, 9)}  {verdict:<9} {focus_mark}")

        if verdict == "L2 SKIP":
            skip_candidates.append((regime, band, d_full, f["n"]))
        if is_focus and verdict in ("L2 SKIP", "MARGIN"):
            focus_hits.append((regime, band, verdict, d_full, d_a, d_b, f["n"]))

    lines.append("")
    lines.append("=" * 108)
    lines.append("FOCUS-CELL SUMMARY (08-12 wg_l2_windblend_cell_concern)")
    lines.append("=" * 108)
    for (regime, band) in sorted(FOCUS_CELLS):
        f = accum.get(("FULL", regime, band))
        if not f or f["n"] == 0:
            lines.append(f"  {regime}/{band}: no data")
            continue
        hit = next((h for h in focus_hits if h[0] == regime and h[1] == band), None)
        if hit:
            _, _, verdict, d_full, d_a, d_b, n = hit
            lines.append(f"  {regime}/{band}: {verdict} — Δ full {d_full:+.1f}% "
                         f"(A {d_a:+.1f}% / B {d_b:+.1f}%), n={n:,}")
        else:
            m_l1_f, m_l2_f = mae(f, "ae_l1"), mae(f, "ae_l2")
            d = None
            if m_l1_f and m_l2_f is not None:
                d = 100.0 * (m_l2_f - m_l1_f) / m_l1_f
            d_s = f"{d:+.1f}%" if d is not None else "—"
            lines.append(f"  {regime}/{band}: KEEP/MARGIN — Δ full {d_s}, n={f['n']:,}")

    lines.append("")
    lines.append("=" * 108)
    if not skip_candidates:
        lines.append("VERDICT: NO L2 SKIP candidates cleared halves + full at floor. "
                     "Either wg L2 is fine cell-wide, or the concern is elsewhere in the stack.")
    else:
        lines.append(f"VERDICT: STAGE 0 — {len(skip_candidates)} L2 SKIP candidate(s):")
        for (regime, band, d, n) in sorted(skip_candidates, key=lambda x: -x[2]):
            lines.append(f"  ({regime}, {band}): Δ +{d:.1f}% n={n:,}")
        lines.append("  Advance to Stage 1: repeat with tighter n floor and confirm on rolling gate. "
                     "Then propose L2 SKIP_TABLE entry mirroring the L3 one.")
    lines.append("=" * 108)

    text = "\n".join(lines)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)


if __name__ == "__main__":
    main()
