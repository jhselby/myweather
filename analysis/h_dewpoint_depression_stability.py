"""Stage 0b — Direction-stability of dp t/dp attribution across rolling windows.

Companion to h_dewpoint_depression.py (Stage 0). Answers the question left
open on project_hypothesis_backlog #6:

  "Aggregate depression bias flipped signs across June-July for the
   candidate regimes. Did the DP-DOMINANT classification hold across
   those flips, or is the pooled DP-DOMINANT verdict a lucky-mix that
   would evaporate on a fresh window?"

Method: split pair-log time range into 4 non-overlapping 8-day chunks.
For each (chunk × regime), compute t_bias, dp_bias, dep_bias, and the
same 5-way classification as the parent script. Flag classification
FLIPS and magnitude decay across chunks.

Focus on the 3 DP-DOMINANT ★ regimes from the 07-28 v0.6.383a pooled
run (pre_frontal, nw_flow, sw_flow). Also reports frontal (BOTH-COMPOUND ★)
for completeness.

Ship rule: DP-DOMINANT attribution must hold as classification in ≥ 3 of
4 chunks AND magnitude must not decay below ⚠ (0.8°F) in any chunk. Any
chunk classifying as T-DOMINANT or NOISE breaks the stability claim →
regime should NOT enter Stage 1 dp-correction workup.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

# 4 non-overlapping 8-day chunks covering 06-26 → 07-28.
CHUNKS = [
    ("C1", "2026-06-26", "2026-07-04"),
    ("C2", "2026-07-04", "2026-07-12"),
    ("C3", "2026-07-12", "2026-07-20"),
    ("C4", "2026-07-20", "2026-07-28"),
]

FOCUS_REGIMES = ["pre_frontal", "nw_flow", "sw_flow", "frontal"]

MIN_N_CHUNK = 200


def chunk_of(run_time):
    if not run_time or len(run_time) < 10:
        return None
    day = run_time[:10]
    for name, lo, hi in CHUNKS:
        if lo <= day < hi:
            return name
    return None


def classify(t_b, dp_b):
    at, ad = abs(t_b), abs(dp_b)
    if max(at, ad) < 0.5:
        return "NOISE"
    if at >= 1.5 * ad and at >= 0.5:
        return "T-DOMINANT"
    if ad >= 1.5 * at and ad >= 0.5:
        return "DP-DOMINANT"
    if (t_b > 0) != (dp_b > 0) and at >= 0.5 and ad >= 0.5:
        return "BOTH-COMPOUND"
    return "BOTH-CANCEL"


def dep_flag(dep_b):
    a = abs(dep_b)
    return "★" if a >= 1.5 else ("⚠" if a >= 0.8 else "")


# Pass 1: join t/dp per (obs_time, lead, run_time) — same as base script
joined = defaultdict(dict)
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in ("t", "dp"):
            continue
        rt = r.get("run_time")
        ch = chunk_of(rt)
        if ch is None:
            continue
        key = (r.get("obs_time"), r.get("lead_h"), rt)
        if None in key:
            continue
        fc = r.get("forecast_l4") or r.get("forecast_l3") or r.get("forecast_l2") or r.get("forecast_l1")
        obs = r.get("observed")
        if fc is None or obs is None:
            continue
        regime = (r.get("state_obs") or {}).get("regime_synoptic")
        joined[key][f] = (fc, obs, regime, ch)

# Aggregate per (chunk, regime)
agg = defaultdict(lambda: {"n": 0, "t_sum": 0.0, "dp_sum": 0.0})
for key, fields in joined.items():
    if "t" not in fields or "dp" not in fields:
        continue
    t_fc, t_obs, regime, ch = fields["t"]
    dp_fc, dp_obs, _, _ = fields["dp"]
    if not regime:
        continue
    a = agg[(ch, regime)]
    a["n"] += 1
    a["t_sum"] += (t_fc - t_obs)
    a["dp_sum"] += (dp_fc - dp_obs)

# ── Emit per-regime chunk table ─────────────────────────────────────────
print("=" * 90)
print("DP ATTRIBUTION DIRECTION-STABILITY — per 8-day chunk")
print("=" * 90)
print("Chunks (each 8 days, non-overlapping):")
for name, lo, hi in CHUNKS:
    print(f"  {name}: {lo} → {hi}")
print(f"MIN_N per chunk: {MIN_N_CHUNK}")
print()

overall_stability = {}

for regime in FOCUS_REGIMES:
    print(f"─── {regime} " + "─" * (85 - len(regime)))
    print(f"{'chunk':<6} {'n':>7} {'dep_bias':>9} {'t_bias':>8} {'dp_bias':>8}  {'source':<15} flag")
    classes = []
    magnitudes = []
    for name, _, _ in CHUNKS:
        a = agg[(name, regime)]
        n = a["n"]
        if n < MIN_N_CHUNK:
            print(f"{name:<6} {n:>7} {'THIN':>9}")
            classes.append("THIN")
            continue
        t_b = a["t_sum"] / n
        dp_b = a["dp_sum"] / n
        dep_b = t_b - dp_b
        cls = classify(t_b, dp_b)
        classes.append(cls)
        magnitudes.append(abs(dep_b))
        print(f"{name:<6} {n:>7,} {dep_b:>+9.2f} {t_b:>+8.2f} {dp_b:>+8.2f}  {cls:<15} {dep_flag(dep_b)}")
    # Stability summary
    n_dp_dom = sum(1 for c in classes if c == "DP-DOMINANT")
    n_valid = sum(1 for c in classes if c != "THIN")
    min_mag = min(magnitudes) if magnitudes else 0.0
    flipped = any(c not in ("DP-DOMINANT", "THIN") for c in classes)
    if n_dp_dom >= 3 and min_mag >= 0.8 and not flipped:
        verdict = "STABLE ✓"
    elif n_dp_dom >= 3 and min_mag >= 0.8:
        verdict = "MOSTLY-STABLE (non-DPD chunk present)"
    elif n_dp_dom >= 2:
        verdict = "MIXED (attribution not stable)"
    else:
        verdict = "UNSTABLE (attribution flips)"
    overall_stability[regime] = verdict
    print(f"→ stability: {verdict}  (DP-DOMINANT in {n_dp_dom}/{n_valid} chunks; "
          f"min |dep|={min_mag:.2f})")
    print()

print("=" * 90)
print("SHIP-GATE READ")
print("=" * 90)
print("Ship rule: DP-DOMINANT in ≥3/4 chunks AND min |dep_bias| ≥ 0.8°F in every")
print("chunk that classifies. STABLE → dp-side correction candidate can enter Stage 1.")
print()
for regime in FOCUS_REGIMES:
    verdict = overall_stability.get(regime, "?")
    marker = "→ CLEARS" if verdict.startswith("STABLE") else "→ HOLDS"
    print(f"  {regime:<14} {verdict:<40} {marker}")
