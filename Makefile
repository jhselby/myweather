deploy-collector:
	gcloud functions deploy myweather-collector \
	  --gen2 \
	  --runtime=python311 \
	  --region=us-east1 \
	  --source=. \
	  --entry-point=run \
	  --trigger-http \
	  --allow-unauthenticated \
	  --timeout=300s \
	  --memory=512MB \
	  --update-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811 \
	  --set-secrets=WU_API_KEY=wu-api-key:latest,PIRATE_WEATHER_API_KEY=PIRATE_WEATHER_API_KEY:latest,GEMINI_API_KEY=gemini-api-key:latest,EBIRD_API_KEY=ebird-api-key:latest

run-collector:
	curl -X POST https://myweather-collector-25c6bclx5q-ue.a.run.app

logs:
	gcloud functions logs read myweather-collector --region=us-east1 --limit=50

run-local:
	@bash -lc 'set +x; set -a; source .env; set +a; python3 -c "from weather_collector.collector import run; run(None)"'
