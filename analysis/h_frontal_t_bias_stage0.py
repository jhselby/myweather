"""Stage 0 — Frontal-regime t over-forecast bias, per-lead-band with
direction-stability halves check.

Motivated by h_dewpoint_depression.py's attribution split (07-28): frontal
regime classified as BOTH-COMPOUND with t_bias +1.47°F and dp_bias -1.63°F,
dep_bias +3.11°F (largest of any regime). The dp side shipped 08-04 as
dpbp (v0.6.391 antecedent-error specialist), leaving the +1.47°F t half
untouched.

08-11 fresh regime pool over last 45d shows frontal t_bias +1.76°F on
n=1,716 — sign held from 07-28 read, magnitude grew slightly. Warrants
Stage 0 per-lead breakdown with a direction-stability halves check before
scoping a frontal_t_bias.py specialist.

Method:
  1. Filter pair log to (field=t, state_fc.regime_synoptic == "frontal").
  2. Split rows into halves by obs_time (older half vs newer half).
  3. Per lead band, compute t_bias (fc - obs) + MAE + n for each half.
  4. Verdict per band:
       * SIGN_HOLDS if both halves have same sign AND |bias| >= 0.5 in both
       * SIGN_FLIPS if halves disagree (kill)
       * THIN if either half n < MIN_N_PER_BAND
  5. Overall: eligible for Stage 1 if all non-THIN bands SIGN_HOLDS positive
     (over-forecast) AND at least 2 bands qualify.

Blocker (per backlog #7): frontal n is small (~1,716 over 45d, ~400-500
per band). If a band comes back THIN, note it; wait 2-3 weekly reads
before scoping a lead-decay fit.
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
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_frontal_t_bias_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_frontal_t_bias_stage0.json")

WINDOW_DAYS = 45
BANDS = [
    ("0-5h",   0, 6),
    ("6-11h",  6, 12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]
MIN_N_PER_BAND = 60
BIAS_FLOOR = 0.5   # halves must both clear this in the same direction
STAGE0_MAGNITUDE_FLOOR = 1.0  # overall pooled bias must clear this to matter

# Stage 1 rolling gate — mirrors l6_fix_b_refit.py's shape. Accumulates the
# ship_bands set across daily runs. Gate clears when ≥ GATE_WINDOW_DAYS
# distinct days in window, no HOLD days, ship_bands stable, ≥1 band shipping.
# Wired 2026-08-12 per Stage 0 verdict's "warrants a Stage 1 direction-
# stability watch (2-3 weekly reads) before scoping specialist."
GATE_HISTORY_PATH = os.path.join(os.path.dirname(SCRIPT_DIR),
                                 ".cache_frontal_t_bias_stage0_history.json")
GATE_HISTORY_RETENTION_DAYS = 30
GATE_WINDOW_DAYS = 7


def _band(lead):
    if lead is None:
        return None
    for lbl, lo, hi in BANDS:
        if lo <= lead < hi:
            return lbl
    return None


def _append_and_summarize_gate_history(this_entry):
    """Append today's entry, prune to retention, compute 7-day rolling gate.
    Same shape as l6_fix_b_refit._append_and_summarize_gate_history; key is
    ship_bands (sorted list of shipped band labels)."""
    try:
        with open(GATE_HISTORY_PATH) as fh:
            history = json.load(fh)
    except FileNotFoundError:
        history = {"entries": []}
    except Exception as e:
        print(f"  ⚠ gate history load failed: {e} — starting fresh")
        history = {"entries": []}

    entries = history.get("entries", [])
    entries.append(this_entry)

    now = datetime.now()
    cutoff_ret = (now - timedelta(days=GATE_HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    entries = [e for e in entries if e.get("fitted_at", "") >= cutoff_ret]
    with open(GATE_HISTORY_PATH, "w") as fh:
        json.dump({"entries": entries}, fh, indent=2)

    cutoff_win = (now - timedelta(days=GATE_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    window = [e for e in entries if e.get("fitted_at", "") >= cutoff_win]

    by_day = {}
    for e in window:
        day = e.get("fitted_at", "")[:10]
        if day:
            by_day.setdefault(day, []).append(e)

    hit_days = 0
    hold_days = 0
    for _day, day_entries in by_day.items():
        if all(x.get("verdict") == "STAGE 0 HIT" for x in day_entries):
            hit_days += 1
        else:
            hold_days += 1

    streak = 0
    for e in reversed(window):
        if e.get("verdict") == "STAGE 0 HIT":
            streak += 1
        else:
            break

    current_bands = set(this_entry.get("ship_bands") or [])
    changed = []
    seen = set()
    for e in reversed(window[:-1]):
        prior = set(e.get("ship_bands") or [])
        for k in current_bands ^ prior:
            if k in seen:
                continue
            seen.add(k)
            was = "SHIP" if k in prior else "not-SHIP"
            now_v = "SHIP" if k in current_bands else "not-SHIP"
            changed.append((k, was, now_v))

    stable = len(changed) == 0
    gate_clear = (len(by_day) >= GATE_WINDOW_DAYS and hold_days == 0
                  and stable and len(current_bands) > 0)

    return {
        "entries_in_window": len(window),
        "days_in_window": len(by_day),
        "hit_days": hit_days,
        "hold_days": hold_days,
        "latest_streak_hit": streak,
        "ship_band_stability": {
            "stable": stable,
            "current_ship_bands": sorted(current_bands),
            "bands_changed_in_window": changed,
        },
        "gate_clear": gate_clear,
        "history_window_days": GATE_WINDOW_DAYS,
    }


def _format_gate_summary(gate):
    lines = []
    lines.append("Frontal t-bias Stage 1 rolling gate:")
    lines.append(f"  window: {gate['history_window_days']} days · runs seen: {gate['entries_in_window']} · "
                 f"distinct days: {gate['days_in_window']}")
    lines.append(f"  hit_days: {gate['hit_days']} · hold_days: {gate['hold_days']} · "
                 f"latest STAGE 0 HIT streak: {gate['latest_streak_hit']}")
    stab = gate["ship_band_stability"]
    lines.append(f"  ship_bands stability: {'STABLE' if stab['stable'] else 'CHURN'} · "
                 f"current bands: {stab['current_ship_bands']}")
    if stab["bands_changed_in_window"]:
        lines.append("  bands whose status changed within window:")
        for k, was, now_v in stab["bands_changed_in_window"]:
            lines.append(f"    {k}: {was} → {now_v}")
    lines.append(f"  gate_clear: {gate['gate_clear']}   "
                 f"(requires ≥{GATE_WINDOW_DAYS} distinct days, no HOLD days, ship_bands STABLE, ≥1 band)")
    return lines


def main():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI

    rows = []
    n_scanned = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "t":
                continue
            ot = r.get("obs_time") or ""
            if ot < lo_win or ot >= hi_win:
                continue
            sfc = (r.get("state_fc") or {}).get("regime_synoptic")
            if sfc != "frontal":
                continue
            fc = (r.get("forecast_l4") or r.get("forecast_l3")
                  or r.get("forecast_l2") or r.get("forecast_l1")
                  or r.get("forecast"))
            obs = r.get("observed")
            lh = r.get("lead_h")
            if fc is None or obs is None or lh is None:
                continue
            band = _band(lh)
            if band is None:
                continue
            rows.append({"vt": r.get("valid_time") or ot, "ot": ot,
                         "band": band, "bias": fc - obs, "abs": abs(fc - obs)})

    if not rows:
        print("VERDICT: INSUFFICIENT DATA — no frontal-regime t rows in window.")
        return 0

    rows.sort(key=lambda x: x["ot"])
    midpoint = len(rows) // 2
    halfA = rows[:midpoint]
    halfB = rows[midpoint:]
    a_start = halfA[0]["ot"][:10]
    a_end = halfA[-1]["ot"][:10]
    b_start = halfB[0]["ot"][:10]
    b_end = halfB[-1]["ot"][:10]

    def per_band(rows_subset):
        out = {}
        by_band = defaultdict(list)
        for r in rows_subset:
            by_band[r["band"]].append(r)
        for band, v in by_band.items():
            biases = [x["bias"] for x in v]
            abss = [x["abs"] for x in v]
            out[band] = {"n": len(v),
                         "t_bias": round(mean(biases), 3),
                         "mae": round(mean(abss), 3)}
        return out

    pooled = per_band(rows)
    halfA_stats = per_band(halfA)
    halfB_stats = per_band(halfB)

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 0 — frontal-regime t over-forecast bias, per lead band, direction-stability halves")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Halves split by obs_time midpoint.")
    lines.append(f"Half A: {a_start} → {a_end}  (n={len(halfA):,})")
    lines.append(f"Half B: {b_start} → {b_end}  (n={len(halfB):,})")
    lines.append(f"Total frontal-regime t rows: {len(rows):,}  (scanned {n_scanned:,}).")
    lines.append(f"Bias floor per half: |bias| >= {BIAS_FLOOR}°F.  "
                 f"Pooled magnitude floor: {STAGE0_MAGNITUDE_FLOOR}°F.")
    lines.append(f"Min n per band per half: {MIN_N_PER_BAND}.")
    lines.append("")
    lines.append(f"{'band':>8}  {'pool_n':>7}  {'pool_bias':>10}  {'A_n':>5}  {'A_bias':>8}  "
                 f"{'B_n':>5}  {'B_bias':>8}  verdict")
    lines.append("-" * 100)

    band_verdicts = {}
    ship_bands = []
    for band, _lo, _hi in BANDS:
        p = pooled.get(band, {"n": 0})
        a = halfA_stats.get(band, {"n": 0})
        b = halfB_stats.get(band, {"n": 0})
        if a["n"] < MIN_N_PER_BAND or b["n"] < MIN_N_PER_BAND:
            verdict = "THIN"
        else:
            a_b = a["t_bias"]
            b_b = b["t_bias"]
            same_sign = (a_b > 0 and b_b > 0) or (a_b < 0 and b_b < 0)
            both_clear = abs(a_b) >= BIAS_FLOOR and abs(b_b) >= BIAS_FLOOR
            if same_sign and both_clear:
                verdict = "SIGN_HOLDS"
                if a_b > 0 and b_b > 0 and p.get("t_bias", 0) >= STAGE0_MAGNITUDE_FLOOR:
                    ship_bands.append(band)
            elif same_sign:
                verdict = "WEAK_MAGNITUDE"
            else:
                verdict = "SIGN_FLIPS"
        band_verdicts[band] = verdict

        p_bias_s = f"{p['t_bias']:+.2f}" if p.get("t_bias") is not None else "-"
        a_bias_s = f"{a['t_bias']:+.2f}" if a.get("t_bias") is not None else "-"
        b_bias_s = f"{b['t_bias']:+.2f}" if b.get("t_bias") is not None else "-"
        lines.append(f"{band:>8}  {p['n']:>7,}  {p_bias_s:>10}  "
                     f"{a['n']:>5,}  {a_bias_s:>8}  "
                     f"{b['n']:>5,}  {b_bias_s:>8}  {verdict}")
    lines.append("")

    if not ship_bands:
        if any(v == "THIN" for v in band_verdicts.values()):
            day_verdict = "HOLD"
            lines.append("VERDICT: HOLD — one or more bands THIN. Frontal-regime n is small; "
                         "re-run in 1-2 weeks as more passages accumulate.")
        else:
            day_verdict = "HOLD"
            lines.append("VERDICT: NO SIGNAL — no band clears direction-stability + magnitude gate. "
                         "Do not scope a frontal_t_bias.py specialist.")
    else:
        day_verdict = "STAGE 0 HIT"
        lines.append(f"VERDICT: STAGE 0 HIT — {len(ship_bands)} band(s) clear direction-stability + "
                     f"pooled magnitude gate: {', '.join(ship_bands)}.")

    # Stage 1 rolling gate — accumulate today's read, report gate state.
    gate = _append_and_summarize_gate_history({
        "fitted_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "verdict": day_verdict,
        "ship_bands": ship_bands,
        "pooled_bias_by_band": {b: pooled.get(b, {}).get("t_bias") for b in [x[0] for x in BANDS]},
    })
    lines.append("")
    lines.extend(_format_gate_summary(gate))

    # Escalate to a STAGE 1 verdict once the gate clears.
    if gate["gate_clear"]:
        lines.append(f"VERDICT: STAGE 1 CLEAR — direction stability held across "
                     f"{gate['days_in_window']} days on bands {ship_bands}. "
                     f"Scope frontal_t_bias.py specialist.")
    elif day_verdict == "STAGE 0 HIT":
        need = max(0, GATE_WINDOW_DAYS - gate["days_in_window"])
        lines.append(f"VERDICT: STAGE 0 HIT (day-only) · STAGE 1 GATE {gate['days_in_window']}/{GATE_WINDOW_DAYS} "
                     f"(need {need} more day(s); ship_bands "
                     f"{'STABLE' if gate['ship_band_stability']['stable'] else 'CHURN'})")

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
            "n_total": len(rows),
            "pooled": pooled,
            "halfA": {"start": a_start, "end": a_end, "stats": halfA_stats},
            "halfB": {"start": b_start, "end": b_end, "stats": halfB_stats},
            "band_verdicts": band_verdicts,
            "ship_bands": ship_bands,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
