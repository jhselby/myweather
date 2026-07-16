"""Rule 5 automation — grep the debug page for stale date/counter refs.

Codifies the transition-invalidation-sweep discipline that failed twice
on 2026-07-16 (v0.6.352c missed 10+ refs Joe had to catch). Scans
corrections_debug.html for the specific patterns that go stale as the
week rolls forward, and reports any that are more than STALE_DAYS old.

Deliberately narrow — only flags predictive-tense refs (day-counters,
"earliest ship / flip", "HOLD until", "as of"). Historical mentions
("shipped 07-12 v0.6.327", "07-13 marathon") are left alone, because
those describe past facts that don't rot.

Run:
    python3 scripts/check_stale_refs.py                # today = system date
    python3 scripts/check_stale_refs.py 2026-07-17     # override today

Exit code: 0 if clean, 1 if any stale refs found (suitable for pre-commit
or CI wiring).
"""
import os
import re
import sys
from datetime import date, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBUG_PAGE = os.path.join(REPO_ROOT, "corrections_debug.html")

# Anything older than this in a predictive-tense ref is stale.
STALE_DAYS = 2

# Patterns to check. Each entry is (name, regex, extractor).
# The regex must have exactly one capture group that returns "MM-DD".
# The extractor is what appears in the error message so a human can grep.
PATTERNS = [
    (
        "day-counter with date tag",
        # Matches: "day 3/7 (07-14)", "Day 4/7 today (07-16)", "gate day N/7 (MM-DD)"
        re.compile(r"[Dd]ay\s+\d+/7[^(]*\((\d{2}-\d{2})\)"),
    ),
    (
        "counter 'as of MM-DD'",
        # Matches: "day 5/7 as of 07-14", "counter as of 07-16"
        re.compile(r"[Dd]ay\s+\d+/7\s+as\s+of\s+(\d{2}-\d{2})", re.IGNORECASE),
    ),
    (
        "'HOLD until MM-DD' past date",
        re.compile(r"HOLD until (?:20\d\d-)?(\d{2}-\d{2})"),
    ),
    (
        "'earliest ship 20XX-MM-DD' past date",
        re.compile(r"[Ee]arliest\s+(?:ship|flip)\s+(?:20\d\d-)?(\d{2}-\d{2})"),
    ),
    (
        "'flip until MM-DD' past date",
        re.compile(r"[Ff]lip\s+until\s+(?:20\d\d-)?(\d{2}-\d{2})"),
    ),
    (
        "Anomaly-week HOLD to MM-DD past date",
        re.compile(r"[Aa]nomaly-week\s+HOLD\s+to\s+(?:20\d\d-)?(\d{2}-\d{2})"),
    ),
]

# Year for MM-DD parses. Assumes the debug page only cares about the
# current year — will need extending if we ever roll into 2027.
YEAR = None  # set in main()


def parse_mmdd(mmdd: str):
    """Parse 'MM-DD' → date object in YEAR. Returns None on garbage."""
    m = re.match(r"^(\d{2})-(\d{2})$", mmdd)
    if not m:
        return None
    try:
        return date(YEAR, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def scan_file(path, today: date):
    """Scan one file for stale refs. Returns list of (line_no, pattern_name, ref_date_str, days_stale, snippet)."""
    stale = []
    with open(path, encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            for name, regex in PATTERNS:
                for m in regex.finditer(line):
                    mmdd = m.group(1)
                    ref = parse_mmdd(mmdd)
                    if ref is None:
                        continue
                    days_stale = (today - ref).days
                    if days_stale > STALE_DAYS:
                        # Snippet: 60 chars around the match
                        start = max(0, m.start() - 20)
                        end = min(len(line), m.end() + 40)
                        snippet = line[start:end].strip()
                        stale.append((line_no, name, mmdd, days_stale, snippet))
    return stale


def main():
    global YEAR
    if len(sys.argv) > 1:
        try:
            today = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"usage: {sys.argv[0]} [YYYY-MM-DD]", file=sys.stderr)
            return 2
    else:
        today = date.today()
    YEAR = today.year

    if not os.path.exists(DEBUG_PAGE):
        print(f"missing: {DEBUG_PAGE}", file=sys.stderr)
        return 2

    stale = scan_file(DEBUG_PAGE, today)

    print(f"Rule 5 check — {DEBUG_PAGE}")
    print(f"Today: {today}   Stale threshold: {STALE_DAYS} days")
    print("=" * 90)
    if not stale:
        print("  ✓ clean — no stale predictive-tense refs.")
        return 0

    # Group by pattern for readability
    by_pattern = {}
    for row in stale:
        by_pattern.setdefault(row[1], []).append(row)

    for name, rows in sorted(by_pattern.items()):
        print(f"\n[{name}]  ({len(rows)} hit{'s' if len(rows) != 1 else ''})")
        for line_no, _, mmdd, days_stale, snippet in rows:
            print(f"  line {line_no:>5}  ref={mmdd}  ({days_stale}d old)   …{snippet}…")

    print(f"\n  ✗ {len(stale)} stale ref{'s' if len(stale) != 1 else ''} found. Fix them or override with a date arg.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
