deploy-collector:
	gcloud functions deploy myweather-collector \
	  --gen2 \
	  --runtime=python311 \
	  --region=us-east1 \
	  --source=. \
	  --entry-point=run \
	  --trigger-http \
	  --no-allow-unauthenticated \
	  --timeout=1800s \
	  --memory=1536MB \
	  --max-instances=1 \
	  --update-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811,GEMINI_MODEL=gemini-2.5-flash-lite \
	  --set-secrets=WU_API_KEY=wu-api-key:latest,PIRATE_WEATHER_API_KEY=PIRATE_WEATHER_API_KEY:latest,GEMINI_API_KEY=gemini-api-key:latest,EBIRD_API_KEY=ebird-api-key:latest,GROQ_API_KEY=groq-api-key:latest

run-collector:
	gcloud scheduler jobs run myweather-collector-schedule --location=us-east1

logs:
	gcloud functions logs read myweather-collector --region=us-east1 --limit=50

run-local:
	@bash -lc 'set +x; set -a; source .env; set +a; python3 -c "from weather_collector.collector import run; run(None)"'

# Note: the old `make analyze` target (bundled all *_summary.txt files
# into analysis/output/_combined.txt for manual upload) was superseded by
# `analysis/runlog/run_digest.sh`, which runs every script and builds a
# structured DIGEST.txt with executive summary, pass/fail table, per-
# script verdicts, and streak counters. If you want a raw all-scripts
# run, invoke run_digest.sh directly. Removed 2026-07-16 as dead code.

# Rule 5 check — grep the debug page for stale predictive-tense refs
# (day counters, "earliest flip / ship", "HOLD until", "as of MM-DD").
# Historical refs left alone. Exit 1 on any hit. See scripts/check_stale_refs.py.
check-stale:
	@python3 scripts/check_stale_refs.py

# Run all analyses WITH chart generation. Slower (matplotlib). Produces
# PNGs alongside text summaries for visual exploration. Use this when you
# want to *see* the patterns, not just read the numbers.
visualize:
	@for f in analysis/*.py; do \
	  echo ""; \
	  echo "═══════════════════════════════════════════════════════════════"; \
	  echo "▶ $$f"; \
	  echo "═══════════════════════════════════════════════════════════════"; \
	  python3 "$$f" || echo "   (failed — continuing)"; \
	done
	@echo ""
	@echo "Charts in analysis/output/:"
	@ls -1 analysis/output/*.png 2>/dev/null
	@open analysis/output/ 2>/dev/null || true
