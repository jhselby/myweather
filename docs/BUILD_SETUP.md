# MyWeather Build Setup Guide

## Overview

This guide covers the automated cache-busting build system that ensures browsers always load fresh JS/CSS files.

---

## The Cache Problem

**Issue:** Browsers aggressively cache JavaScript and CSS files. When you update `app-main.js`, users' browsers serve the old cached version instead of downloading the new file.

**Old solution:** Manual `?v=4.12` version strings  
**Problem with old solution:** Easy to forget, hard to maintain, version numbers don't match content

**New solution:** Automated content-based hashing  
**How it works:** `build.py` calculates SHA-256 hash of each file's contents and appends it automatically

---

## Quick Start

### Every Time You Modify JS/CSS Files

```bash
cd ~/Documents/myweather

# 1. Make your code changes
# (edit js/app-main.js, styles/app.css, etc.)

# 2. Run build script
python3 build.py

# 3. Commit everything
git add .
git commit -m "v4.12: Your changes"
git push
```

**That's it.** The build script handles all cache busting automatically.

---

## What build.py Does

1. **Scans index.html** for all `<script src="...">` and `<link href="...">`
2. **Calculates hash** of each file's contents (SHA-256, first 8 characters)
3. **Rewrites index.html** with `?v=HASH` appended to each asset
4. **Creates backup** as `index.html.backup` (just in case)

### Example Output

```
============================================================
MyWeather Build - Cache Busting
============================================================

📂 Working directory: /Users/you/Documents/myweather
📄 Processing: /Users/you/Documents/myweather/index.html

🔍 Found 3 asset(s) to process:
  • js/app-main.js
  • js/changelog_loader.js
  • styles/app.css

💾 Backup created: index.html.backup

✅ Updated index.html with cache-busting hashes:
  ✓ js/app-main.js → ?v=a1b2c3d4
  ✓ js/changelog_loader.js → ?v=e5f6g7h8
  ✓ styles/app.css → ?v=i9j0k1l2

============================================================
Build complete! Commit index.html to deploy changes.
============================================================
```

---

## How It Works

### Before (Manual Versioning)
```html
<script src="js/app-main.js?v=4.12"></script>
<link href="styles/app.css?v=4.12">
```

**Problems:**
- Forgot to update version → users get stale code
- Version doesn't change when file doesn't change → wastes commits
- Version changes when file doesn't change → forces unnecessary downloads

### After (Automated Hashing)
```html
<script src="js/app-main.js?v=a1b2c3d4"></script>
<link href="styles/app.css?v=e5f6a7b8">
```

**Benefits:**
- Hash changes ONLY when file contents change
- Impossible to forget (just run build.py)
- Content-based versioning (what real production apps do)

---

## Workflow Integration

### Option 1: Pre-Commit Hook (Automated)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/sh
# Auto-run build.py before every commit

echo "Running cache-busting build..."
python3 build.py

if [ $? -eq 0 ]; then
    # Add updated index.html to commit
    git add index.html
    echo "✅ Build complete, index.html updated"
else
    echo "❌ Build failed"
    exit 1
fi
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

Now build.py runs automatically on every `git commit`.

### Option 2: Manual (Current)

Just remember to run `python3 build.py` before committing.

---

## Advanced Usage

### Check What Would Change (Dry Run)

```bash
python3 build.py
# Look at output, don't commit if suspicious
```

### Restore from Backup

If build.py made a mistake:
```bash
cp index.html.backup index.html
```

### Force Rebuild All Hashes

```bash
# Edit any file to change timestamp
touch js/app-main.js
python3 build.py
```

---

## File Structure

```
myweather/
├── build.py                    ← The build script
├── index.html                  ← Modified by build.py
├── index.html.backup           ← Created by build.py (gitignored)
├── js/
│   ├── app-main.js            ← Source file (you edit this)
│   ├── changelog_loader.js    ← Source file
│   └── overhead.js            ← Source file
└── styles/
    └── app.css                ← Source file (you edit this)
```

**You edit:** Source files (JS/CSS)  
**build.py edits:** Only index.html (adds hashes)  
**You commit:** Everything (sources + updated index.html)

---

## Troubleshooting

### "⚠️ Warning: js/app-main.js not found"

**Cause:** build.py can't find the file referenced in index.html  
**Fix:** Check file path is correct, file exists

### "No changes made - all assets already up to date"

**Cause:** You didn't modify any JS/CSS files since last build  
**Fix:** This is normal! No build needed if files haven't changed

### Users still seeing old cached files

**Cause:** They need to hard-refresh once after the change  
**Fix:** Tell them to shift-reload (Shift+Cmd+R on Mac)  
**Prevention:** After this first refresh, they'll always get fresh files automatically

---

## Comparison: Before vs After

### Manual Versioning (Before)
```bash
# Edit app-main.js
# Edit index.html to change v=4.11 to v=4.12
# Edit app.css
# Edit index.html to change v=4.11 to v=4.12 again
# Edit CHANGELOG.md
# Forgot to update changelog_loader.js version!
# Users get stale changelog loader
# Debug for 20 minutes
git add . && git commit -m "v4.12"
```

### Automated Hashing (After)
```bash
# Edit app-main.js
# Edit app.css  
# Edit CHANGELOG.md
python3 build.py
git add . && git commit -m "v4.12"
# Everything just works
```

---

## Integration with Existing Workflow

Your current workflow:
1. Make code changes
2. Update version in index.html manually
3. Commit and push

New workflow:
1. Make code changes
2. ~~Update version manually~~ Run `python3 build.py`
3. Commit and push

**One extra command, infinite fewer cache bugs.**

---

## Why This Matters

**Cache bugs are silent failures.** User reports "the app is broken" but for you it works fine. You spend 20 minutes debugging before realizing they just need to shift-reload.

**This system eliminates that entire class of bugs.** File changes → hash changes → browser downloads new version automatically.

---

## Questions?

**Q: Do I need to run build.py if I only change Python files?**  
A: No. Only run it when you modify JS/CSS files that index.html references.

**Q: Do I need to run build.py if I only change docs/?**  
A: No. Markdown files are fetched at runtime, they auto-update.

**Q: What if I modify index.html structure (not assets)?**  
A: Run build.py anyway - it's safe and ensures consistency.

**Q: Can I manually edit the ?v= hashes?**  
A: Don't. Let build.py manage them. Manual edits will be overwritten next build.

**Q: What if build.py has a bug and breaks index.html?**  
A: Restore from `index.html.backup` and report the bug.

---

## Summary

**Problem solved:** Browser cache bugs  
**Time cost:** 2 seconds per commit (`python3 build.py`)  
**Time saved:** Hours of cache debugging  
**Bonus:** Professional-grade asset versioning  

**Just remember:** Edit code → `python3 build.py` → commit.
