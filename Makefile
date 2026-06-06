deploy-collector:
	gcloud functions deploy myweather-collector \
	  --gen2 \
	  --runtime=python311 \
	  --region=us-east1 \
	  --source=. \
	  --entry-point=run \
	  --trigger-http \
	  --no-allow-unauthenticated \
	  --timeout=540s \
	  --memory=1024MB \
	  --max-instances=1 \
	  --update-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811,GEMINI_MODEL=gemini-2.5-flash \
	  --set-secrets=WU_API_KEY=wu-api-key:latest,PIRATE_WEATHER_API_KEY=PIRATE_WEATHER_API_KEY:latest,GEMINI_API_KEY=gemini-api-key:latest,EBIRD_API_KEY=ebird-api-key:latest,GROQ_API_KEY=groq-api-key:latest

run-collector:
	gcloud scheduler jobs run myweather-collector-schedule --location=us-east1

logs:
	gcloud functions logs read myweather-collector --region=us-east1 --limit=50

run-local:
	@bash -lc 'set +x; set -a; source .env; set +a; python3 -c "from weather_collector.collector import run; run(None)"'

# Run all analyses in TEXT-ONLY mode (skip matplotlib chart generation) and
# concatenate every summary into a single bundle for easy upload.
# Use `make analyze` for the fast text-only path.
analyze:
	@rm -f analysis/output/_combined.txt
	@for f in analysis/*.py; do \
	  echo ""; \
	  echo "═══════════════════════════════════════════════════════════════"; \
	  echo "▶ $$f"; \
	  echo "═══════════════════════════════════════════════════════════════"; \
	  ANALYSIS_NO_CHARTS=1 python3 "$$f" || echo "   (failed — continuing)"; \
	done
	@echo ""
	@echo "Bundling summaries → analysis/output/_combined.txt"
	@for s in analysis/output/*_summary.txt; do \
	  printf "\n\n=== %s ===\n\n" "$$(basename "$$s")" >> analysis/output/_combined.txt; \
	  cat "$$s" >> analysis/output/_combined.txt; \
	done
	@echo "Done — upload analysis/output/_combined.txt"

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
