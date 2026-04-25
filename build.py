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
    4. Creates index.html.backup before modifying (just in case)
    
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
    
    if not changes:
        print("\n⚠️  No changes made - all assets already up to date or missing")
        return 0
    
    # Backup original
    backup_path = index_path.with_suffix('.html.backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"\n💾 Backup created: {backup_path}")
    
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


if __name__ == '__main__':
    exit(main())
