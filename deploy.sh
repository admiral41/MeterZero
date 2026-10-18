#!/usr/bin/env bash
# Deploy MeterZero to Google Cloud Run (Cloud Build builds the container; no local Docker needed).
#
#   ./deploy.sh YOUR_PROJECT_ID            # Gemini with an AI Studio key (asks for it once)
#   ./deploy.sh YOUR_PROJECT_ID vertex     # Gemini through Vertex AI (no key)
#
# The key is stored in Secret Manager as "gemini-api-key", never in the image or the repository.
set -euo pipefail

PROJECT="${1:?usage: ./deploy.sh PROJECT_ID [apikey|vertex]}"
AUTH="${2:-apikey}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-meterzero}"

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com aiplatform.googleapis.com

NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
ACCOUNT="serviceAccount:${NUMBER}-compute@developer.gserviceaccount.com"

if [[ "$AUTH" == "vertex" ]]; then
  gcloud projects add-iam-policy-binding "$PROJECT" --member="$ACCOUNT" --role=roles/aiplatform.user --condition=None >/dev/null
  GEMINI=(--set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global")
else
  if [[ -z "$(gcloud secrets list --filter='name~gemini-api-key$' --format='value(name)')" ]]; then
    read -rsp "Paste your Gemini API key (from aistudio.google.com/apikey): " KEY; echo
    printf '%s' "$KEY" | gcloud secrets create gemini-api-key --data-file=- --replication-policy=automatic >/dev/null
    unset KEY
  fi
  gcloud secrets add-iam-policy-binding gemini-api-key --member="$ACCOUNT" --role=roles/secretmanager.secretAccessor >/dev/null
  GEMINI=(--set-secrets "GEMINI_API_KEY=gemini-api-key:latest")
fi

gcloud run deploy "$SERVICE" --source . --region "$REGION" --allow-unauthenticated \
  --memory 2Gi --cpu 2 --timeout 3600 --session-affinity --min-instances 0 --max-instances 3 "${GEMINI[@]}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo "MeterZero is live at: $URL   (check $URL/api/health and $URL/api/ai/status)"
