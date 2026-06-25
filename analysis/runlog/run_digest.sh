#!/bin/bash
# Run every analysis/*.py, extract verdict/headline lines, write one digest
# with an executive summary at the top (deltas vs prior run).
cd /Users/josephselby/Documents/myweather
TOOL_DIR=analysis/runlog          # tracked tooling
LOG_DIR=analysis/output/runlog    # gitignored artifacts
DIGEST=analysis/output/DIGEST.txt
STATUS_TSV=$LOG_DIR/run_status.tsv
mkdir -p "$LOG_DIR"

: > "$STATUS_TSV"

# Body section accumulates first; executive summary is prepended at the end.
BODY=$(mktemp)
trap 'rm -f "$BODY"' EXIT

{
  echo "MyWeather analysis digest — $(date)"
  echo ""
  echo "=================================================="
  echo "PASS / FAIL TABLE"
  echo "=================================================="
} > "$BODY"

for f in analysis/*.py; do
  name=$(basename "$f" .py)
  [ "$name" = "_cache" ] && continue
  out="$LOG_DIR/${name}.log"
  start=$(date +%s)

  python3 -m analysis."$name" >"$out" 2>&1
  rc=$?
  if [ $rc -ne 0 ] && grep -q "No module named '_cache'" "$out"; then
    python3 "$f" >"$out" 2>&1
    rc=$?
  fi

  dur=$(( $(date +%s) - start ))
  if [ $rc -eq 0 ]; then
    status="OK     "
  elif grep -qE "^(VERDICT|Verdict|→ [A-Z]|RESULT:)" "$out"; then
    # Non-zero exit but the script printed a verdict line — this is the
    # "didn't meet ship threshold" exit code pattern (r4_spread_analysis,
    # walkforward variants under some conditions). Treat as OK so it
    # doesn't squat in "Needs attention" every run.
    status="OK     "
  else
    status="FAIL($rc)"
  fi
  printf "  %-9s %4ds  %s\n" "$status" "$dur" "$name" >> "$BODY"
  printf "%s\t%s\t%s\n" "$name" "$status" "$dur" >> "$STATUS_TSV"
done

{
  echo ""
  echo "=================================================="
  echo "PER-SCRIPT FINDINGS (verdict lines + tail context)"
  echo "=================================================="
} >> "$BODY"

while IFS=$'\t' read -r name status secs; do
  out="$LOG_DIR/${name}.log"
  {
    echo ""
    echo "------------------------------------------------------------------"
    echo "[$status] $name"
    echo "------------------------------------------------------------------"
  } >> "$BODY"

  verdict=$(grep -nE "VERDICT|→ (SHIP|HOLD|KILL|PROMOTE|MARGINAL|CLOSE|WASH|REVIVE|RETIRE|DEFER|NOT READY|READY)|^Verdict:|recommend:|RECOMMEND|RESULT:" "$out" 2>/dev/null | head -8)
  if [ -n "$verdict" ]; then
    echo "  verdict lines:" >> "$BODY"
    echo "$verdict" | sed 's/^/    /' >> "$BODY"
  fi
  echo "  tail:" >> "$BODY"
  tail -15 "$out" | sed 's/^/    /' >> "$BODY"
done < "$STATUS_TSV"

echo "" >> "$BODY"
echo "Run finished $(date)" >> "$BODY"

# Build executive summary + divergence report, prepend to body, write final digest.
EXEC_SUM=$(python3 "$TOOL_DIR/build_executive_summary.py")
DIVERGENCE=$(python3 "$TOOL_DIR/divergence_report.py")
{
  echo "$EXEC_SUM"
  echo ""
  echo "$DIVERGENCE"
  echo ""
  cat "$BODY"
} > "$DIGEST"

echo "Digest: $DIGEST"
wc -l "$DIGEST"
