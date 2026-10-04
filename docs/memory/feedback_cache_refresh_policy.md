---
name: feedback-cache-refresh-policy
description: Convention for when to force-refresh the analysis cache (_cache.py) vs reuse stale data. No cron — natural rhythm of the audit cadence.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a8831ed-d0ae-48ad-9c90-349a29eadd94
---

Don't build a cron / scheduled refresh for `_cache.py`. The natural rhythm of the audit cadence is the right policy.

**Rules:**
- **Date-gated audits (06-19, 06-22 re-runs, walk-forward, R5/L5 ship/hold reads) always force fresh.** Set `MYWEATHER_REFRESH=1` when running. The data has to be from this morning for the verdict to count.
- **Mid-week exploration uses whatever's cached.** Tweaking thresholds, debugging, comparing variants — 12h-stale data is fine. Don't burn egress for an experimental run.
- **Print cache age at script start** so it's always obvious whether you're looking at fresh or stale data. e.g., `📦 pair log: cached 4h ago (935 MB)`.

**Why:** Joe runs ~3-5 audits a week. A cron would refresh data on a schedule that doesn't match when the audits actually run. Forcing the operator to think "is this an official decision-grade run?" before flipping the env var is the right cognitive load — it matches the discipline of the audit pattern itself ("don't ship without two consecutive agreeing audits").

**How to apply:** When building a new analysis script, default to `cached_path(url)` (12h freshness). Document at the top: "run with `MYWEATHER_REFRESH=1` for decision-grade output." Don't add per-script age overrides unless there's a specific reason.

## Related

- [[feedback-analysis-cache]] — the base rule that all `analysis/` scripts must use `_cache.py`, not `urlopen`.
