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
	  --memory=2048MB \
	  --max-instances=1 \
	  --update-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811,GEMINI_MODEL=gemini-2.5-flash-lite \
	  --set-secrets=WU_API_KEY=wu-api-key:latest,PIRATE_WEATHER_API_KEY=PIRATE_WEATHER_API_KEY:latest,GEMINI_API_KEY=gemini-api-key:latest,EBIRD_API_KEY=ebird-api-key:latest,GROQ_API_KEY=groq-api-key:latest

run-collector:
	gcloud scheduler jobs run myweather-collector-schedule --location=us-east1

logs:
	gcloud functions logs read myweather-collector --region=us-east1 --limit=50

# Publisher — runs the 6 dashboard-data rollups hourly, publishes JSON to GCS
# for the debug page. See publisher/main.py.
deploy-publisher:
	gcloud functions deploy myweather-publisher \
	  --gen2 \
	  --runtime=python311 \
	  --region=us-east1 \
	  --source=. \
	  --entry-point=publish \
	  --trigger-http \
	  --no-allow-unauthenticated \
	  --timeout=540s \
	  --memory=2048MB \
	  --max-instances=1 \
	  --update-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811

run-publisher:
	gcloud scheduler jobs run myweather-publisher-schedule --location=us-east1

logs-publisher:
	gcloud functions logs read myweather-publisher --region=us-east1 --limit=50

# NBM backfill — one-shot CF that pulls historical NBM CO extracts and writes
# gs://myweather-data/nbm_backfill/YYYYMMDD_HH.json per cycle. Resume-friendly.
# Deploy once; invoke repeatedly with ?start_date=&num_days= until 120d covered.
deploy-nbm-backfill:
	gcloud functions deploy myweather-nbm-backfill \
	  --gen2 \
	  --runtime=python311 \
	  --region=us-east1 \
	  --source=. \
	  --entry-point=backfill \
	  --trigger-http \
	  --no-allow-unauthenticated \
	  --timeout=3600s \
	  --memory=4096MB \
	  --cpu=2 \
	  --max-instances=10 \
	  --update-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811

# Backfill CF is I/O-bound (byte-range fetches from NBM S3), not CPU-bound.
# Downsized from 8vCPU/8GB to 2vCPU/4GB on 2026-08-19 after cost audit —
# per-invocation cost dropped ~$0.76 -> ~$0.20. Throughput per-cycle nearly
# identical because the bottleneck is network + cfgrib decode ordering.

logs-nbm-backfill:
	gcloud functions logs read myweather-nbm-backfill --region=us-east1 --limit=50

# NBM hourly ingester — fetches freshest NBM cycle each hour, writes
# nbm_point_extract.json to GCS for the collector to stamp raw_nbm from.
deploy-nbm-ingester:
	gcloud functions deploy myweather-nbm-ingest \
	  --gen2 \
	  --runtime=python311 \
	  --region=us-east1 \
	  --source=. \
	  --entry-point=nbm_ingest \
	  --trigger-http \
	  --no-allow-unauthenticated \
	  --timeout=540s \
	  --memory=2048MB \
	  --cpu=2 \
	  --max-instances=2 \
	  --update-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811

logs-nbm-ingester:
	gcloud functions logs read myweather-nbm-ingest --region=us-east1 --limit=50

run-nbm-ingester:
	gcloud scheduler jobs run myweather-nbm-ingest-schedule --location=us-east1

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
	  case "$$f" in *.skip.py) continue ;; esac; \
	  name=$$(basename "$$f" .py); \
	  echo ""; \
	  echo "═══════════════════════════════════════════════════════════════"; \
	  echo "▶ $$f"; \
	  echo "═══════════════════════════════════════════════════════════════"; \
	  python3 -m analysis."$$name" || echo "   (failed — continuing)"; \
	done
	@echo ""
	@echo "Charts in analysis/output/:"
	@ls -1 analysis/output/*.png 2>/dev/null
	@open analysis/output/ 2>/dev/null || true
