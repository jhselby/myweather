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
	  --set-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811

run-collector:
	curl -X POST https://us-east1-weather-data-493811.cloudfunctions.net/myweather-collector

logs:
	gcloud functions logs read myweather-collector --region=us-east1 --limit=50
