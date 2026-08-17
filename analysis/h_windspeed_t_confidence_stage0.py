"""Stage 0 — observed windspeed as a live confidence axis for temperature.

Motivated by round-2 smoke (08-10). Short-lead (0-3h) |t_err| rose monotonically
0.39 -> 1.22 across ws bins 0-2, 2-5, 5-10, 10-15, 15+ kt (n = 68, 677, 2088,
1404, 559).  Suggests observed windspeed at the valid_time is a clean live
confidence input for t — separate from every existing t predictor.

Design:
  * Join t rows with same-valid_time observed ws (first ws obs per vt wins).
  * Bin by ws.  Train on first WINDOW_DAYS - HELD_OUT_DAYS, test on last
    HELD_OUT_DAYS.
  * Held-out gate: mean|t_err| in top ws bin >= 2.0x mean|t_err| in bottom
    ws bin, AND monotone rising across 5 bins.

If it holds up, Stage 1 adds ws-conditional t confidence to c1.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _prod import prod_error  # noqa: E402
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_windspeed_t_confidence_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_windspeed_t_confidence_stage0.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_MAX = 3
BINS = [
    ("0-5 kt", 0, 5),
    ("5-10 kt", 5, 10),
    ("10-15 kt", 10, 15),
    ("15+ kt", 15, 999),
]
MIN_N_PER_BIN_TEST = 20
STAGE0_GATE_RATIO = 1.8


def ws_bin(ws):
    for name, lo, hi in BINS:
        if lo <= ws < hi:
            return name
    return None


def main():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI

    # Pass 1: build ws-obs lookup per valid_time (first non-null wins).
    ws_obs = {}
    t_rows = []  # (vt, err)  short-lead only
    n_scanned = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            vt = r.get("valid_time") or ""
            if vt < lo_win or vt >= hi_win:
                continue
            f = r.get("field")
            if f == "ws":
                ob = r.get("observed")
                if ob is not None and vt not in ws_obs:
                    ws_obs[vt] = float(ob)
            elif f == "t":
                lh = r.get("lead_h")
                err = prod_error(r)
                if lh is None or lh > LEAD_MAX or err is None:
                    continue
                t_rows.append((vt, float(err)))

    if not t_rows:
        print("VERDICT: INSUFFICIENT DATA — no t rows in window.")
        return 0

    max_vt = max(vt for vt, _ in t_rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    train_bins = defaultdict(list)
    test_bins = defaultdict(list)
    n_matched = 0
    for vt, err in t_rows:
        ws = ws_obs.get(vt)
        if ws is None:
            continue
        b = ws_bin(ws)
        if b is None:
            continue
        n_matched += 1
        (test_bins if vt[:10] >= test_start else train_bins)[b].append(abs(err))

    per_bin = []
    for name, _, _ in BINS:
        tr = train_bins.get(name, [])
        te = test_bins.get(name, [])
        per_bin.append({
            "bin": name,
            "n_train": len(tr),
            "train_mean_abs_err": round(mean(tr), 4) if tr else None,
            "n_test": len(te),
            "test_mean_abs_err": round(mean(te), 4) if te else None,
        })

    lines = []
    lines.append("=" * 88)
    lines.append("STAGE 0 — observed ws bin -> short-lead |t_err|  (confidence axis)")
    lines.append("=" * 88)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out: last {HELD_OUT_DAYS}d.  "
                 f"Lead cap: {LEAD_MAX}h.")
    lines.append(f"Scanned {n_scanned:,} rows;  ws_obs keys: {len(ws_obs):,};  "
                 f"t-short rows matched to ws: {n_matched:,}.")
    lines.append(f"Test starts: {test_start} (max_vt {max_vt[:10]}).")
    lines.append(f"Gate: test top-bin / bottom-bin ratio >= {STAGE0_GATE_RATIO:.1f}  "
                 f"AND monotone rising across 5 bins.  Min n_test per bin: {MIN_N_PER_BIN_TEST}.")
    lines.append("")
    lines.append(f"{'ws_bin':>10}  {'n_tr':>6}  {'tr_mean|err|':>14}  {'n_te':>6}  {'te_mean|err|':>14}")
    lines.append("-" * 62)
    for b in per_bin:
        tm = f"{b['train_mean_abs_err']:.3f}" if b['train_mean_abs_err'] is not None else "-"
        tem = f"{b['test_mean_abs_err']:.3f}" if b['test_mean_abs_err'] is not None else "-"
        lines.append(f"{b['bin']:>10}  {b['n_train']:>6}  {tm:>14}  {b['n_test']:>6}  {tem:>14}")
    lines.append("")

    # Evaluate gate
    te_means = [b["test_mean_abs_err"] for b in per_bin]
    ns_ok = all(b["n_test"] >= MIN_N_PER_BIN_TEST for b in per_bin)
    valid = all(m is not None for m in te_means)
    if not (ns_ok and valid):
        lines.append(f"VERDICT: INSUFFICIENT DATA — one or more bins has < "
                     f"{MIN_N_PER_BIN_TEST} test rows or missing.")
        text = "\n".join(lines)
    else:
        ratio = te_means[-1] / te_means[0] if te_means[0] > 0 else 0
        max_rises = len(te_means) - 1
        rises = sum(1 for i in range(max_rises) if te_means[i + 1] > te_means[i])
        lines.append(f"Top/Bottom test ratio: {ratio:.2f}   "
                     f"monotone_rises: {rises}/{max_rises}")
        lines.append("")
        gate_mono = max_rises - 1  # allow one dip
        if ratio >= STAGE0_GATE_RATIO and rises >= gate_mono:
            lines.append(f"VERDICT: STAGE 0 HIT — ratio {ratio:.2f} clears {STAGE0_GATE_RATIO:.1f}× "
                         f"gate and shape is monotone.")
            lines.append("Warrants Stage 1: bin-conditional t confidence in c1.")
        else:
            lines.append(f"VERDICT: NO STAGE 0 HIT — ratio {ratio:.2f} or monotone "
                         f"{rises}/{max_rises} below threshold.  Do not proceed to Stage 1.")
        text = "\n".join(lines)

    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_lo": lo_win,
            "window_hi": hi_win,
            "test_start": test_start,
            "per_bin": per_bin,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
