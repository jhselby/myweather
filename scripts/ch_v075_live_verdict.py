"""v0.7.5 ch verdict: score the live ims-threshold router on its own picks.

For every pair-log row with field == ch and selector_mechanism == ims_threshold:
  picked  = |error| of the source the router chose (selector_source)
  other   = |error| of the source it did not choose
  hrrr    = |error_l4|            always-HRRR policy
  nbm     = |error_l3_nbm|, else |error_raw_nbm|   always-NBM policy
  served  = |error|               what users saw (router pick + any later layer)

The router earns its keep when picked < other (it chose the better source on
average) and picked < min(hrrr, nbm) is the strong form. Reads the live pair
log only: ims_threshold stamps exist only on post-v0.7.7 rows.

Run from the repo root:  python3 scripts/ch_v075_live_verdict.py
Set MYWEATHER_REFRESH=1 to force a fresh pair-log download.
"""
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from analysis._cache import cached_path, PAIR_LOG_URL

CELLS = {
    ("ne_flow", "0-5"), ("ne_flow", "12-23"), ("nw_flow", "24-47"),
    ("pre_frontal", "0-5"), ("pre_frontal", "6-11"), ("pre_frontal", "12-23"),
    ("se_flow", "6-11"), ("se_flow", "12-23"), ("se_flow", "24-47"),
    ("sw_flow", "12-23"),
}
MIN_N = 30
FAIL_PCT = -5.0


def band(lead):
    for label, lo, hi in (("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)):
        if lo <= lead < hi:
            return label
    return None


def load():
    rows = []
    n_ims = n_drop = 0
    with open(cached_path(PAIR_LOG_URL)) as fh:
        for line in fh:
            if '"ims_threshold"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("field") != "ch" or r.get("selector_mechanism") != "ims_threshold":
                continue
            n_ims += 1
            nbm = r.get("error_l3_nbm")
            if nbm is None:
                nbm = r.get("error_raw_nbm")
            src = r.get("selector_source")
            eh, es = r.get("error_l4"), r.get("error")
            lead = r.get("lead_h")
            regime = (r.get("state_fc") or {}).get("regime_synoptic")
            if None in (nbm, eh, es, lead) or src not in ("hrrr", "nbm") or not regime or band(int(lead)) is None:
                n_drop += 1
                continue
            eh, en, es = abs(float(eh)), abs(float(nbm)), abs(float(es))
            picked, other = (en, eh) if src == "nbm" else (eh, en)
            rows.append({
                "t": r.get("obs_time", ""), "key": (regime, band(int(lead))),
                "nbm_pick": src == "nbm", "eh": eh, "en": en, "es": es,
                "picked": picked, "other": other,
            })
    rows.sort(key=lambda x: x["t"])
    return rows, n_ims, n_drop


def mean(rows, k):
    return sum(r[k] for r in rows) / len(rows)


def summarize(rows):
    n = len(rows)
    m = {k: mean(rows, k) for k in ("picked", "other", "eh", "en", "es")}
    best_fixed = min(m["eh"], m["en"])
    m.update(n=n, nbm_frac=sum(r["nbm_pick"] for r in rows) / n,
             lift_other=100 * (m["other"] - m["picked"]) / m["other"] if m["other"] else 0.0,
             lift_best=100 * (best_fixed - m["picked"]) / best_fixed if best_fixed else 0.0)
    return m


def verdict(m, halves):
    if m["n"] < MIN_N:
        return "THIN"
    if m["lift_best"] < FAIL_PCT or m["lift_other"] <= 0:
        return "FAILING"
    if m["lift_best"] >= 0 and all(h["lift_other"] > 0 for h in halves if h["n"] >= MIN_N // 2):
        return "HOLDING"
    return "MARGINAL"


def main():
    rows, n_ims, n_drop = load()
    print(f"ch ims_threshold rows: {n_ims}  usable: {len(rows)}  dropped (missing field): {n_drop}")
    if not rows:
        print("No rows. Pair log is stale or the mechanism stamp is absent.")
        return
    print(f"window: {rows[0]['t']} .. {rows[-1]['t']}")
    by_cell = defaultdict(list)
    off = []
    for r in rows:
        (by_cell[r["key"]] if r["key"] in CELLS else off).append(r)

    hdr = f"{'cell':<22}{'n':>5}{'nbm%':>6}{'picked':>8}{'other':>8}{'hrrr':>8}{'nbm':>8}{'served':>8}{'vs other':>10}{'vs best':>9}  halves(vs other)  verdict"
    print("\n" + hdr)
    print("-" * len(hdr))
    tally = defaultdict(int)
    for key in sorted(CELLS):
        cr = by_cell.get(key, [])
        if not cr:
            print(f"{key[0] + '/' + key[1]:<22}{0:>5}  no rows")
            tally["THIN"] += 1
            continue
        m = summarize(cr)
        mid = len(cr) // 2
        hv = [summarize(h) if h else {"n": 0, "lift_other": 0.0} for h in (cr[:mid], cr[mid:])]
        v = verdict(m, hv)
        tally[v] += 1
        print(f"{key[0] + '/' + key[1]:<22}{m['n']:>5}{100*m['nbm_frac']:>6.0f}{m['picked']:>8.2f}{m['other']:>8.2f}"
              f"{m['eh']:>8.2f}{m['en']:>8.2f}{m['es']:>8.2f}{m['lift_other']:>+9.1f}%{m['lift_best']:>+8.1f}%"
              f"  {hv[0]['lift_other']:+6.1f}% / {hv[1]['lift_other']:+6.1f}%  {v}")
    cell_rows = [r for k in CELLS for r in by_cell.get(k, [])]
    print("-" * len(hdr))
    if cell_rows:
        m = summarize(cell_rows)
        print(f"{'ALL 10 CELLS':<22}{m['n']:>5}{100*m['nbm_frac']:>6.0f}{m['picked']:>8.2f}{m['other']:>8.2f}"
              f"{m['eh']:>8.2f}{m['en']:>8.2f}{m['es']:>8.2f}{m['lift_other']:>+9.1f}%{m['lift_best']:>+8.1f}%")
    if off:
        keys = defaultdict(int)
        for r in off:
            keys[r["key"]] += 1
        top = ", ".join(f"{k[0]}/{k[1]}:{c}" for k, c in sorted(keys.items(), key=lambda x: -x[1])[:5])
        m = summarize(off)
        print(f"\noff-cell rows (pair-log regime differs from runtime regime): {len(off)}  "
              f"picked {m['picked']:.2f} vs other {m['other']:.2f}  top: {top}")

    print("\nby day (all ims_threshold rows): n, picked, other, hrrr, nbm")
    days = defaultdict(list)
    for r in rows:
        days[r["t"][:10]].append(r)
    for d in sorted(days):
        m = summarize(days[d])
        print(f"  {d}  n={m['n']:>4}  {m['picked']:.2f}  {m['other']:.2f}  {m['eh']:.2f}  {m['en']:.2f}")

    print(f"\nTALLY: {tally['HOLDING']} HOLDING / {tally['MARGINAL']} MARGINAL / "
          f"{tally['FAILING']} FAILING / {tally['THIN']} THIN (of {len(CELLS)} cells)")
    print(f"Rules: THIN n<{MIN_N}; FAILING vs best fixed policy < {FAIL_PCT}% or picked >= other; "
          f"HOLDING vs best >= 0 and both halves beat the unchosen source.")


if __name__ == "__main__":
    main()
