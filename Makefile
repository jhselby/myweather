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
	  --set-env-vars=GOOGLE_CLOUD_PROJECT=weather-data-493811,WU_API_KEY=e1f10a1e78da46f5b10a1e78da96f525,PIRATE_WEATHER_API_KEY=0mvXH6VSOmo8f5r1G3882vSQ5OVXB13i,EBIRD_API_KEY=sjjc0p5rqpqg

run-collector:
	curl -X POST https://myweather-collector-25c6bclx5q-ue.a.run.app

logs:
	gcloud functions logs read myweather-collector --region=us-east1 --limit=50
