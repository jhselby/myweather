#!/bin/bash
# Weekly server-side copy of gs://myweather-data into a rotating slot of
# gs://myweather-data-backup (slot = ISO week mod 4, overwritten in place, no deletes).
# Server-side: nothing is downloaded, no egress. Backup bucket has soft delete and
# versioning OFF; do not enable either (the live bucket rewrites ~100 GB/day).
# Status: ~/.local/state/myweather-backup/status.json (also copied to the backup bucket).
set -u
export PATH=/opt/homebrew/bin:/opt/homebrew/share/google-cloud-sdk/bin:/usr/bin:/bin

SRC=gs://myweather-data
DST=gs://myweather-data-backup
SLOT=$(( 10#$(date +%V) % 4 ))
STATE="$HOME/.local/state/myweather-backup"
mkdir -p "$STATE"
STARTED=$(date -u +%FT%TZ)

write_status() {
  printf '{"ok": %s, "slot": %s, "started": "%s", "finished": "%s", "src_bytes": %s, "dst_bytes": %s, "note": "%s"}\n' \
    "$1" "$SLOT" "$STARTED" "$(date -u +%FT%TZ)" "${2:-0}" "${3:-0}" "$4" > "$STATE/status.json"
  gcloud storage cp "$STATE/status.json" "$DST/_status.json" >/dev/null 2>&1
}

if ! gcloud storage cp -r "$SRC/*" "$DST/slot-$SLOT/" >"$STATE/last_run.log" 2>&1; then
  write_status false 0 0 "copy failed, see last_run.log"
  exit 1
fi

src_b=$(gcloud storage du -s "$SRC" 2>/dev/null | awk '{print $1}')
dst_b=$(gcloud storage du -s "$DST/slot-$SLOT" 2>/dev/null | awk '{print $1}')
# the source keeps changing during the copy, so allow 5% drift
if [ -n "$src_b" ] && [ -n "$dst_b" ] && [ "$dst_b" -ge $(( src_b * 95 / 100 )) ]; then
  write_status true "$src_b" "$dst_b" "ok"
  # Last step, success only: Hawtch Watcher watches this file's age (no Google credentials needed).
  touch "$HOME/Developer/myweather/backup_last_ok"
else
  write_status false "${src_b:-0}" "${dst_b:-0}" "size check failed"
  exit 1
fi
