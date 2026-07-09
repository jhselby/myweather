#!/usr/bin/env python3
"""Applied-layer consistency checker — CLI wrapper.

Actual audit logic lives in
`weather_collector/processors/applied_layer_audit.py` (also called from
the Fitter preflight). This wrapper prints the human-readable report and
exits 1 on any failure so the nightly digest and CI can gate on it.

Usage:
  python3 analysis/applied_layer_audit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from weather_collector.processors.applied_layer_audit import run_audit, format_report

if __name__ == "__main__":
    ok, passes, failures = run_audit()
    for line in format_report(passes, failures):
        print(line)
    sys.exit(0 if ok else 1)
