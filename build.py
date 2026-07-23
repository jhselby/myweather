#!/usr/bin/env python3
"""
MyWeather Build Script - Cache Busting Automation

Automatically adds content-based version hashes to all JS/CSS assets in index.html.
Run before every commit to ensure browsers get fresh files.

Usage:
    python3 build.py

What it does:
    1. Reads all JS/CSS files referenced in index.html
    2. Calculates SHA-256 hash of each file's contents
    3. Rewrites index.html with ?v=HASH appended to each asset
    
Example:
    <script src="js/app-main.js"></script>
    becomes
    <script src="js/app-main.js?v=abc123"></script>
"""

import re
import hashlib
from pathlib import Path


def calculate_file_hash(filepath):
    """Calculate SHA-256 hash of file contents, return first 8 chars."""
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
            hash_obj = hashlib.sha256(content)
            return hash_obj.hexdigest()[:8]
    except FileNotFoundError:
        print(f"⚠️  Warning: {filepath} not found, skipping")
        return None


def extract_assets(html_content):
    """
    Extract all JS and CSS asset paths from HTML.
    Returns dict: {original_tag: filepath}
    """
    assets = {}
    
    # Match <script src="path/to/file.js">
    script_pattern = r'<script\s+src=["\']([^"\'?]+)(?:\?[^"\']*)?["\'][^>]*>'
    for match in re.finditer(script_pattern, html_content):
        full_tag = match.group(0)
        filepath = match.group(1)
        if filepath.startswith(('http://', 'https://')):
            continue
        assets[full_tag] = filepath
    
    # Match <link rel="stylesheet" href="path/to/file.css">
    css_pattern = r'<link\s+[^>]*href=["\']([^"\'?]+\.css)(?:\?[^"\']*)?["\'][^>]*>'
    for match in re.finditer(css_pattern, html_content):
        full_tag = match.group(0)
        filepath = match.group(1)
        if filepath.startswith(('http://', 'https://')):
            continue
        assets[full_tag] = filepath
    
    return assets


def add_cache_busting(html_content, assets, base_dir):
    """
    Replace asset references with cache-busted versions.
    Returns modified HTML content.
    """
    modified_html = html_content
    changes_made = []
    
    for original_tag, filepath in assets.items():
        # Calculate hash
        full_path = base_dir / filepath
        file_hash = calculate_file_hash(full_path)
        
        if file_hash is None:
            continue
        
        # Build new tag by modifying the original
        # Pattern: Replace src="path" or src="path?v=old" with src="path?v=new"
        if '<script' in original_tag:
            # Match src="filepath" or src="filepath?anything"
            new_tag = re.sub(
                rf'src=["\']({re.escape(filepath)})(?:\?[^"\']*)?["\']',
                rf'src="\1?v={file_hash}"',
                original_tag
            )
        else:  # CSS link tag
            # Match href="filepath" or href="filepath?anything"
            new_tag = re.sub(
                rf'href=["\']({re.escape(filepath)})(?:\?[^"\']*)?["\']',
                rf'href="\1?v={file_hash}"',
                original_tag
            )
        
        # Replace in HTML
        if new_tag != original_tag:
            modified_html = modified_html.replace(original_tag, new_tag)
            changes_made.append(f"  ✓ {filepath} → ?v={file_hash}")
    
    return modified_html, changes_made



def validate_html(html_content):
    """
    Check for mismatched/unclosed tags in HTML.
    Returns list of error strings (empty = clean).
    """
    from html.parser import HTMLParser

    VOID_ELEMENTS = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr'
    }

    errors = []
    stack = []

    class Checker(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag.lower() not in VOID_ELEMENTS:
                stack.append((tag.lower(), self.getpos()))

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag in VOID_ELEMENTS:
                return
            if not stack:
                errors.append(f"Line {self.getpos()[0]}: closing </{tag}> with no matching open tag")
                return
            # Walk back to find matching open tag (allows for browser-style recovery)
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    # Any tags between here and top of stack are unclosed
                    for j in range(len(stack) - 1, i, -1):
                        unclosed = stack[j]
                        errors.append(f"Line {unclosed[1][0]}: <{unclosed[0]}> never closed (closed by </{tag}> at line {self.getpos()[0]})")
                    del stack[i:]
                    return
            errors.append(f"Line {self.getpos()[0]}: closing </{tag}> with no matching open tag")

    try:
        Checker().feed(html_content)
    except Exception as e:
        errors.append(f"Parser error: {e}")
        return errors

    # Anything left on stack is unclosed
    for tag, pos in stack:
        errors.append(f"Line {pos[0]}: <{tag}> never closed")

    return errors

def main():
    """Main build process."""
    print("=" * 60)
    print("MyWeather Build - Cache Busting")
    print("=" * 60)
    
    # Find repo root (where index.html lives)
    base_dir = Path(__file__).parent
    index_path = base_dir / 'index.html'
    
    if not index_path.exists():
        print(f"❌ Error: index.html not found in {base_dir}")
        return 1
    
    print(f"\n📂 Working directory: {base_dir}")
    print(f"📄 Processing: {index_path}")
    
    # Read current index.html
    with open(index_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Validate HTML
    print("\n🔎 Validating HTML...")
    html_errors = validate_html(html_content)
    if html_errors:
        print(f"\n❌ Found {len(html_errors)} HTML issue(s):")
        for err in html_errors:
            print(f"  ⚠️  {err}")
        print("\n⚠️  Proceeding with build, but fix these issues.")
    else:
        print("  ✓ No markup issues found")

    # Extract assets
    assets = extract_assets(html_content)
    print(f"\n🔍 Found {len(assets)} asset(s) to process:")
    for filepath in assets.values():
        print(f"  • {filepath}")
    
    # Add cache-busting hashes
    modified_html, changes = add_cache_busting(html_content, assets, base_dir)
    
    # Write version.json for update detection (always, regardless of asset changes)
    import json, re as _re
    v_match = _re.search(r'id="appVersion"[^>]*>(v[\d.]+[a-z]?)<', modified_html)
    if v_match:
        version_path = base_dir / 'version.json'
        with open(version_path, 'w') as vf:
            json.dump({"version": v_match.group(1)}, vf)
        print(f"  ✓ version.json → {v_match.group(1)}")

        # Bump sw.js CACHE_VERSION to match — without this, the service worker
        # keeps serving the previous version's app shell (index.html, app.css,
        # briefing.css, app-main.js, briefing.js) until the user reloads twice.
        # Root cause of the "no difference" frustration in v0.6.186-189 work.
        sw_path = base_dir / 'sw.js'
        if sw_path.exists():
            with open(sw_path, 'r') as sf:
                sw_content = sf.read()
            new_cache_version = f"wc-{v_match.group(1)}"
            new_sw_content, n_subs = _re.subn(
                r"const CACHE_VERSION = '[^']*';",
                f"const CACHE_VERSION = '{new_cache_version}';",
                sw_content,
                count=1,
            )
            if n_subs and new_sw_content != sw_content:
                with open(sw_path, 'w') as sf:
                    sf.write(new_sw_content)
                print(f"  ✓ sw.js CACHE_VERSION → {new_cache_version}")

    # Cache-bust dynamically-loaded scripts referenced inside JS files
    # (e.g. js/overhead.js loaded via document.createElement('script') in
    # app-main.js). Static <script>/<link> tags are handled by the HTML
    # pass above; this pass picks up the lazy-load case.
    js_dir = base_dir / 'js'
    js_lazy_bumps = []
    if js_dir.is_dir():
        lazy_pattern = re.compile(r"(['\"])(js/([a-z_]+\.js))\?v=[a-f0-9]+\1")
        for js_file in sorted(js_dir.glob('*.js')):
            with open(js_file, 'r') as jf:
                jf_content = jf.read()
            def _swap(m):
                quote, target_path, target_name = m.group(1), m.group(2), m.group(3)
                target_full = base_dir / target_path
                target_hash = calculate_file_hash(target_full)
                if target_hash is None:
                    return m.group(0)
                replacement = f"{quote}{target_path}?v={target_hash}{quote}"
                if replacement != m.group(0):
                    js_lazy_bumps.append(f"  ✓ {js_file.name} → lazy-load {target_path} ?v={target_hash}")
                return replacement
            new_jf_content = lazy_pattern.sub(_swap, jf_content)
            if new_jf_content != jf_content:
                with open(js_file, 'w') as jf:
                    jf.write(new_jf_content)
    for line in js_lazy_bumps:
        print(line)

    # Auto-refresh debug page day counters + last-curated banner. Codified
    # 2026-07-23 after repeated instances of me proposing work based on stale
    # debug page state — the day counter drifted N days past its ship date
    # because Rule 5 sweeps were manual. Machine-enforced counter advancement
    # kills the class. Registry lives at top of function; add on every ship
    # that opens a 14-day watch. Only in-window ships are touched; expired
    # watches (elapsed > watch_days) are left alone for a human to close.
    _refresh_debug_page(base_dir)

    if not changes:
        print("\n⚠️  No changes made - all assets already up to date or missing")
        return 0

    # Write modified HTML
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(modified_html)
    
    print(f"\n✅ Updated index.html with cache-busting hashes:")
    for change in changes:
        print(change)
    
    print("\n" + "=" * 60)
    print("Build complete! Commit index.html to deploy changes.")
    print("=" * 60)
    
    return 0


# Ship events with active 14-day post-ship watches. Each entry:
#   version: the version string that appears on the day-counter line in the
#            debug page (used as the same-line anchor for substitution).
#   date:    ISO ship date. Today's day counter = today − date.
#   watch_days: watch window length (14 for standard post-ship watches).
#
# Add entries here whenever a live-layer change ships. Remove when the watch
# closes cleanly (or leave in place — the refresh only touches in-window ships).
SHIP_EVENTS = [
    {"version": "v0.6.355",  "date": "2026-07-17", "watch_days": 14},  # Lc
    {"version": "v0.6.358",  "date": "2026-07-19", "watch_days": 14},  # ch persistence gate
    {"version": "v0.6.368a", "date": "2026-07-20", "watch_days": 14},  # wd L2 blend
    {"version": "v0.6.370",  "date": "2026-07-20", "watch_days": 14},  # ws L3 asymmetric SKIP
]


def _refresh_debug_page(base_dir):
    """Advance day-counter references on lines that also mention a SHIP_EVENTS
    version, and bump the 'Last curated:' banner to today.

    Regex 'day N/W' on the same line as version string → 'day <elapsed>/W'.
    Version-string anchor keeps stray '14-day' text (e.g. 'day 7/14' as a
    future decision date) from being clobbered — those lines don't carry the
    version. Ships past their watch window are left alone.
    """
    from datetime import date as _dt_date
    debug_path = base_dir / 'corrections_debug.html'
    if not debug_path.is_file():
        return
    today = _dt_date.today()
    content = debug_path.read_text(encoding='utf-8')
    orig_content = content
    changes = []

    for event in SHIP_EVENTS:
        try:
            ship_date = _dt_date.fromisoformat(event["date"])
        except ValueError:
            continue
        elapsed = (today - ship_date).days
        watch = event["watch_days"]
        if elapsed < 0 or elapsed > watch:
            continue
        # Convention: "day 1 = ship day", matches prior changelog usage.
        # (E.g. v0.6.371a advanced Lc from day 4 → 5 on 07-21, four days
        # after Lc shipped 07-17.)
        day_n = elapsed + 1
        version = event["version"]
        # Escape "." in "v0.6.355" for the regex.
        vpat = re.escape(version)
        # Only substitute the counter that immediately follows the version
        # string (up to ~140 chars away — enough for `(v0.6.355, 07-17) — day
        # 7/14` and its variants; short enough not to reach a neighbouring
        # event's counter on the same line). If several ship-events share a
        # line (historical changelog entries), each event's iteration only
        # touches its own nearby counter — not all counters on the line.
        counter_re = re.compile(
            rf"({vpat})([^<]{{0,140}}?\b)(day|Day)( )(\d+)/{watch}\b"
        )
        new_lines = []
        touched_this_event = 0
        for line in content.splitlines(keepends=True):
            if version not in line:
                new_lines.append(line)
                continue
            def _sub(m):
                nonlocal touched_this_event
                old_n = int(m.group(5))
                if old_n == day_n:
                    return m.group(0)
                touched_this_event += 1
                return f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}{day_n}/{watch}"
            new_lines.append(counter_re.sub(_sub, line))
        if touched_this_event:
            changes.append(f"  ✓ {version} → day {day_n}/{watch} "
                           f"({touched_this_event} site{'s' if touched_this_event > 1 else ''})")
        content = "".join(new_lines)

    # Bump 'Last curated:' banner to today. Matches:
    #   Last curated: 2026-07-23 v0.6.375a · click any sub-box...
    curated_re = re.compile(
        r"(Last curated:\s*)(\d{4}-\d{2}-\d{2})(\s+v[\d.]+[a-z]?)"
    )
    today_iso = today.isoformat()
    def _bump_curated(m):
        if m.group(2) == today_iso:
            return m.group(0)
        changes.append(f"  ✓ Last curated → {today_iso}{m.group(3)}")
        return f"{m.group(1)}{today_iso}{m.group(3)}"
    content = curated_re.sub(_bump_curated, content)

    if content != orig_content:
        debug_path.write_text(content, encoding='utf-8')
        for line in changes:
            print(line)


if __name__ == '__main__':
    exit(main())
