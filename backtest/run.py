#!/usr/bin/env python3
"""
Backtest CLI — compare alternative L3/L4 enable configs against the
current production whitelist using the live pair log.

Examples:

  # Compare today's walk-forward verdict against production
  python3 -m backtest.run --candidate walkforward_15jun --days 2

  # Compare a custom L3/L4 set
  python3 -m backtest.run --l3 ws,wg,ch --l4 "" --days 2

  # Inspect raw evaluation for one config
  python3 -m backtest.run --evaluate --l3 ws,wg,ch --l4 "" --days 2

Designed to answer "if we shipped config X today, what would MAE look
like on the last N days of held-out pair-log data?"
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.replay import evaluate_config, compare_configs


# Canonical named configs for quick A/B work.
NAMED_CONFIGS = {
    # Current production (as of v0.6.81)
    "production": {
        "L3_FIELDS": {"ws", "wg", "ch", "cm", "pp"},
        "L4_FIELDS": {"ch"},
    },
    # Today's walk-forward (2026-06-15) verdict — drops cm/pp from L3, clears L4
    "walkforward_15jun": {
        "L3_FIELDS": {"ws", "wg", "ch"},
        "L4_FIELDS": set(),
    },
    # Last week's walk-forward (2026-06-08) verdict — wider L3, L4 = {wg, cm}
    "walkforward_08jun": {
        "L3_FIELDS": {"ws", "wg", "ch", "cm"},
        "L4_FIELDS": {"wg", "cm"},
    },
    # Stable core that BOTH walk-forwards agree on
    "stable_core": {
        "L3_FIELDS": {"ws", "wg", "ch"},
        "L4_FIELDS": set(),
    },
    # All correction layers OFF — baseline
    "l2_only": {"L3_FIELDS": set(), "L4_FIELDS": set()},
}


def _parse_field_set(arg):
    if not arg:
        return set()
    return set(s.strip() for s in arg.split(",") if s.strip())


def _resolve_config(name=None, l3=None, l4=None):
    if name:
        if name not in NAMED_CONFIGS:
            raise SystemExit(f"unknown config name: {name}. Available: {list(NAMED_CONFIGS)}")
        return NAMED_CONFIGS[name]
    return {"L3_FIELDS": _parse_field_set(l3), "L4_FIELDS": _parse_field_set(l4)}


def _print_evaluate(result):
    cfg = result["config"]
    print(f"Config:  L3 = {cfg['L3_FIELDS']}    L4 = {cfg['L4_FIELDS']}")
    print(f"Window:  last {result['test_days']:.1f} days, total {result['total_pairs']:,} pairs")
    print()
    print(f"  {'field':<8} {'n':>8} {'MAE':>10}    layer_dist")
    print(f"  {'-'*8} {'-'*8} {'-'*10}    {'-'*30}")
    for field in sorted(result["per_field"]):
        s = result["per_field"][field]
        layers = ", ".join(f"{k}:{v}" for k, v in sorted(s["layer_dist"].items()))
        mae_str = f"{s['mae']:>10.4f}" if s['mae'] is not None else f"{'--':>10}"
        print(f"  {field:<8} {s['n']:>8} {mae_str}    {layers}")


def _print_compare(result):
    a = result["baseline"]
    b = result["candidate"]
    print(f"BASELINE:  L3 = {a['config']['L3_FIELDS']}  L4 = {a['config']['L4_FIELDS']}")
    print(f"CANDIDATE: L3 = {b['config']['L3_FIELDS']}  L4 = {b['config']['L4_FIELDS']}")
    print(f"Window:    last {a['test_days']:.1f} days")
    print()
    print(f"  {'field':<8} {'n':>8} {'baseline':>10} {'candidate':>10} {'Δ':>10} {'Δ%':>8}    verdict")
    print(f"  {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*8}    {'-'*16}")
    for row in result["comparison"]:
        if row["baseline_mae"] is None or row["candidate_mae"] is None:
            print(f"  {row['field']:<8} {row['n']:>8} {'--':>10} {'--':>10} {'--':>10} {'--':>8}    {row['verdict']}")
            continue
        print(f"  {row['field']:<8} {row['n']:>8} {row['baseline_mae']:>10.4f} {row['candidate_mae']:>10.4f} {row['delta']:>+10.4f} {row['pct']:>+7.2f}%    {row['verdict']}")


def main():
    p = argparse.ArgumentParser(description="Backtest L3/L4 configs against the live pair log")
    p.add_argument("--baseline", default="production", help="named config or use --b-l3/--b-l4")
    p.add_argument("--candidate", default=None, help="named config or use --l3/--l4")
    p.add_argument("--l3", default=None, help="comma-separated L3 fields for candidate")
    p.add_argument("--l4", default=None, help="comma-separated L4 fields for candidate")
    p.add_argument("--b-l3", default=None, dest="b_l3", help="custom baseline L3 fields")
    p.add_argument("--b-l4", default=None, dest="b_l4", help="custom baseline L4 fields")
    p.add_argument("--days", type=float, default=2.0, help="held-out test window in days")
    p.add_argument("--evaluate", action="store_true", help="show single config eval instead of A/B")
    p.add_argument("--json", action="store_true", help="emit JSON instead of table")
    args = p.parse_args()

    if args.evaluate:
        cfg = _resolve_config(name=args.candidate, l3=args.l3, l4=args.l4)
        result = evaluate_config(cfg, test_days=args.days)
        if args.json:
            print(json.dumps(result, indent=2, default=list))
        else:
            _print_evaluate(result)
        return 0

    baseline = _resolve_config(name=args.baseline, l3=args.b_l3, l4=args.b_l4) if (args.b_l3 or args.b_l4) else NAMED_CONFIGS[args.baseline]
    candidate = _resolve_config(name=args.candidate, l3=args.l3, l4=args.l4)
    result = compare_configs(baseline, candidate, test_days=args.days)
    if args.json:
        print(json.dumps(result, indent=2, default=list))
    else:
        _print_compare(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
