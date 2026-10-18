<#
Deploy MeterZero to Google Cloud Run. Cloud Build builds the container from the Dockerfile,
so you don't need Docker on your machine.

    .\deploy.ps1 -Project YOUR_PROJECT_ID                  # Gemini with an AI Studio key (from backend\.env, or asks once)
    .\deploy.ps1 -Project YOUR_PROJECT_ID -Auth vertex     # Gemini through Vertex AI (no key at all)

The key is stored in Secret Manager as "gemini-api-key" and handed to the service at run time.
It is never written into the container image or this repository.
#>
param(
    [string]$Project,
    [string]$Region = "us-central1",
    [string]$Service = "meterzero",
    [ValidateSet("apikey", "vertex")][string]$Auth = "apikey"
)
$ErrorActionPreference = "Stop"

# Settings from backend\.env (the same file the server reads locally).
$envFile = Join-Path $PSScriptRoot "backend\.env"
$settings = @{}
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*([A-Z_]+)\s*=\s*(.+?)\s*$') { $settings[$Matches[1]] = $Matches[2].Trim('"', "'") }
    }
}
if (-not $Project) { $Project = $settings["GOOGLE_CLOUD_PROJECT"] }
if (-not $Project) { throw "Pass -Project YOUR_PROJECT_ID, or set GOOGLE_CLOUD_PROJECT in backend\.env" }

# A project number (all digits) works too: look up its ID.
if ($Project -match '^\d+$') {
    $Project = gcloud projects describe $Project --format="value(projectId)"
    Write-Host "Project number resolved to project ID: $Project"
}

Write-Host "`n1/4  Using project $Project" -ForegroundColor Cyan
gcloud config set project $Project

Write-Host "`n2/4  Turning on the Google Cloud services MeterZero needs (first time takes a minute)" -ForegroundColor Cyan
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
    secretmanager.googleapis.com aiplatform.googleapis.com

# Cloud Run runs as the default compute service account unless told otherwise.
$number = gcloud projects describe $Project --format="value(projectNumber)"
$account = "serviceAccount:$number-compute@developer.gserviceaccount.com"

Write-Host "`n3/4  Connecting Gemini ($Auth)" -ForegroundColor Cyan
if ($Auth -eq "vertex") {
    gcloud projects add-iam-policy-binding $Project --member=$account --role=roles/aiplatform.user --condition=None | Out-Null
    $gemini = @("--set-env-vars", "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$Project,GOOGLE_CLOUD_LOCATION=global")
} else {
    $exists = gcloud secrets list --filter="name~gemini-api-key$" --format="value(name)"
    if (-not $exists) {
        $plain = $settings["GEMINI_API_KEY"]
        if ($plain) {
            Write-Host "     Using GEMINI_API_KEY from backend\.env"
        } else {
            $secure = Read-Host "Paste your Gemini API key (from aistudio.google.com/apikey)" -AsSecureString
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        }
        $file = New-TemporaryFile
        try {
            [IO.File]::WriteAllText($file.FullName, $plain.Trim())   # no trailing newline
            gcloud secrets create gemini-api-key --data-file="$($file.FullName)" --replication-policy=automatic | Out-Null
        } finally {
            Remove-Item $file.FullName -Force
            $plain = $null
        }
        Write-Host "     Stored the key in Secret Manager as gemini-api-key."
    } else {
        Write-Host "     Using the existing gemini-api-key secret. To change it:"
        Write-Host "     gcloud secrets versions add gemini-api-key --data-file=PATH_TO_A_FILE_WITH_THE_KEY"
    }
    gcloud secrets add-iam-policy-binding gemini-api-key --member=$account --role=roles/secretmanager.secretAccessor | Out-Null
    $gemini = @("--set-secrets", "GEMINI_API_KEY=gemini-api-key:latest")
}

Write-Host "`n4/4  Building and deploying (about 5-10 minutes the first time)" -ForegroundColor Cyan
gcloud run deploy $Service --source . --region $Region --allow-unauthenticated `
    --memory 2Gi --cpu 2 --timeout 3600 --session-affinity --min-instances 0 --max-instances 3 @gemini

$url = gcloud run services describe $Service --region $Region --format="value(status.url)"
Write-Host "`nMeterZero is live at: $url" -ForegroundColor Green
Write-Host "Check it:  $url/api/health   and   $url/api/ai/status  (should say connected: true)"
