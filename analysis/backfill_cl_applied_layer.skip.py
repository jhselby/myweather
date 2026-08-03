"""One-shot backfill for cl applied_layer stamps poisoned by the clp
shadow-write and pre-v0.6.389f Lc stamps.

For any cl row where applied_layer ∈ {'clp', 'l6'} but the row's `error`
(what production actually produced) matches a lower-layer error, re-stamp
applied_layer to that lower layer. Production never used the clp shadow
or the pre-Lc value on those rows; the stamp was wrong.

Usage:
    python3 analysis/backfill_cl_applied_layer.py --dry-run
    python3 analysis/backfill_cl_applied_layer.py --apply
    python3 analysis/backfill_cl_applied_layer.py --apply --upload

--dry-run     : count what would change, no writes
--apply       : rewrite the local cache in-place (atomic via temp+rename)
--upload      : after --apply, gsutil cp the corrected file to GCS
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

PAIR_LOG = Path.home() / ".cache" / "myweather" / "forecast_error_log.jsonl"
GCS_URI = "gs://myweather-data/forecast_error_log.jsonl"
FIELD = "cl"
POISONED_STAMPS = {"clp", "l6"}
CANDIDATES = ("l1", "l2", "l3", "l4")
MATCH_TOL = 0.01


def resolve_true_layer(row):
    """Mirror forecast_snapshot._derive_applied_layer: walk layers shallow→deep,
    track the deepest layer where the value (proxied by error) changed. If nothing
    above l1 differs from l1, applied is l1. Final choice must match row['error']."""
    real = row.get("error")
    if real is None:
        return None
    applied = None
    prev = None
    for cand in CANDIDATES:
        e = row.get(f"error_{cand}")
        if e is None:
            continue
        if applied is None:
            applied = cand
            prev = e
        elif abs(e - prev) > MATCH_TOL:
            applied = cand
            prev = e
    if applied is not None and abs(prev - real) < MATCH_TOL:
        return applied
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()

    if not (args.dry_run or args.apply):
        ap.error("pass --dry-run or --apply")
    if args.upload and not args.apply:
        ap.error("--upload requires --apply")

    src = PAIR_LOG
    tmp = PAIR_LOG.with_suffix(".jsonl.backfill_tmp")

    before = Counter()
    after = Counter()
    unresolved = 0
    total_cl = 0
    total_rows = 0

    out_fh = open(tmp, "w") if args.apply else None
    try:
        with open(src) as fh:
            for line in fh:
                total_rows += 1
                if not line.strip():
                    if out_fh:
                        out_fh.write(line)
                    continue
                r = json.loads(line)
                changed = False
                if r.get("field") == FIELD:
                    total_cl += 1
                    al = r.get("applied_layer")
                    before[al or "None"] += 1
                    if al in POISONED_STAMPS:
                        new_layer = resolve_true_layer(r)
                        if new_layer is not None:
                            r["applied_layer"] = new_layer
                            changed = True
                        else:
                            unresolved += 1
                    after[r.get("applied_layer") or "None"] += 1
                if out_fh:
                    if changed:
                        out_fh.write(json.dumps(r) + "\n")
                    else:
                        out_fh.write(line)
    except Exception:
        if out_fh:
            out_fh.close()
            tmp.unlink(missing_ok=True)
        raise

    if out_fh:
        out_fh.close()

    print(f"pair log rows scanned:  {total_rows:,}")
    print(f"cl rows:                {total_cl:,}")
    print(f"unresolved poisoned:    {unresolved:,}  (no matching lower-layer error)")
    print()
    print("cl applied_layer distribution:")
    keys = sorted(set(before) | set(after))
    print(f"  {'layer':>8} {'before':>10} {'after':>10}   {'Δ':>8}")
    for k in keys:
        b = before.get(k, 0)
        a = after.get(k, 0)
        print(f"  {k:>8} {b:>10,} {a:>10,}   {a-b:>+8,}")

    if args.apply:
        os.replace(tmp, src)
        print(f"\n✓ rewrote {src}")
        if args.upload:
            print(f"\nuploading to {GCS_URI} ...")
            subprocess.run(
                ["gsutil", "-h", "Cache-Control:no-cache", "cp",
                 str(src), GCS_URI],
                check=True,
            )
            print("✓ uploaded")


if __name__ == "__main__":
    main()
