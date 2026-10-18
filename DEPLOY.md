# Deploying MeterZero to Google Cloud Run

The AI Builder Cup asks for two things, and this guide covers both:

1. **A Gemini model in the product.** MeterZero calls Gemini through the Google Gen AI SDK, using a key
   from **Google AI Studio** (or Vertex AI).
2. **Deployed on Google Cloud** with **Cloud Run**. One container serves the API and the web app.

Allow about 30 minutes the first time. All commands are for Windows PowerShell, run from `E:\google`.

---

## Step 1. Get a Gemini API key (2 minutes)

1. Open <https://aistudio.google.com/apikey> and sign in with your Google account.
2. Click **Create API key**, then copy it. Treat it like a password: don't paste it into chats, screenshots or code files.

## Step 2. Put the key in the project and test locally (10 minutes)

The key lives in **one file**, `backend\.env`, which git and the container image both ignore.

```powershell
copy backend\.env.example backend\.env
notepad backend\.env
```

Fill in two lines, then save:

```
GEMINI_API_KEY=your-key-from-ai-studio        # starts with AIza
GOOGLE_CLOUD_PROJECT=your-project-id          # or the project number, e.g. 846756383341
```

Now test the AI features against the real Gemini API:

```powershell
.venv\Scripts\python backend\scripts\live_gemini_check.py
```

It runs chat, a follow-up question, the weekly review, the weekly summary and a bill photo read. It then writes
`backend\artifacts\live_gemini_report.md` with a ✅ or ❌ for each. These results are also saved, so the app can
show them if the Wi-Fi fails during the demo.

Then try the whole app locally:

```powershell
cd frontend; npm install; npm run build; cd ..
.venv\Scripts\python -m uvicorn server.main:app --app-dir backend --port 8000
```

Open <http://localhost:8000>. The sidebar should say **Gemini connected**. Try **Ask MeterZero**.

> **Where the key is used in the code:** `backend/server/env.py` loads `backend/.env` at start-up, and
> `backend/meterzero/agent.py` (`make_client`) creates the Gemini client. The routes that call Gemini are
> in `backend/server/ai.py`. You never need to put the key anywhere else.

## Step 3. Set up Google Cloud (10 minutes, once)

1. Open <https://console.cloud.google.com>. New accounts get free trial credit; a billing account is required.
2. Create a project: top bar → project picker → **New project**, for example `meterzero-demo`. Note the
   **project ID** it shows; it may have numbers added, like `meterzero-demo-471203`.
3. Install the Google Cloud CLI:

   ```powershell
   winget install Google.CloudSDK
   ```

   Or use the installer from <https://cloud.google.com/sdk/docs/install>. Then close and reopen PowerShell.

4. Sign in:

   ```powershell
   gcloud auth login
   ```

## Step 4. Deploy (one command, 5–10 minutes)

```powershell
.\deploy.ps1
```

It takes the project and the key from `backend\.env`. You can also pass them: `.\deploy.ps1 -Project YOUR_PROJECT_ID`
(it then asks for the key, hidden, if `backend\.env` has none). A project number works as well as an ID.

What it does:

1. Turns on Cloud Run, Cloud Build, Artifact Registry, Secret Manager and Vertex AI for the project.
2. Stores your Gemini key in **Secret Manager** as `gemini-api-key` (the first time only).
3. Uploads the code. Cloud Build builds the `Dockerfile`: it builds the frontend, installs the backend and
   trains the demo plant.
4. Starts the service on Cloud Run and prints its public URL, for example `https://meterzero-xxxxx-uc.a.run.app`.

If PowerShell refuses to run the script, allow scripts for this window only, then run the deploy command again:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

> **No key at all?** `.\deploy.ps1 -Project YOUR_PROJECT_ID -Auth vertex` uses Gemini through Vertex AI
> with the service's own Google Cloud identity.

## Step 5. Test the deployed app (5 minutes)

Replace `URL` with the address the script printed:

| Check | Expected |
|---|---|
| `URL/api/health` | `{"ok":true}` |
| `URL/api/ai/status` | `"connected":true` |
| `URL` | The Overview page with the demo plant |
| Ask MeterZero → "What should I fix first?" | An answer with the lookups it made |
| Bills & paperwork → **Read this photo with Gemini** | Gemini reads the sample bill |

Logs, if something fails:

```powershell
gcloud run services logs read meterzero --region us-central1 --limit 50
```

## Updating after changes

Run the same command again. It reuses the stored key and replaces the running version with no downtime.

```powershell
.\deploy.ps1
```

To change the key: put the new key alone in a file, then
`gcloud secrets versions add gemini-api-key --data-file=key.txt`, delete the file, and deploy again.

## Costs

* Cloud Run scales to zero when nobody is using it (`--min-instances 0`), and at most 3 copies run (`--max-instances 3`).
* For a hackathon demo this usually stays within the free tier and trial credit. To be safe, set a budget alert in
  the Cloud Console under **Billing → Budgets & alerts**.
* When the judging is over: `gcloud run services delete meterzero --region us-central1`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `gcloud` is not recognised | Reopen PowerShell after installing the CLI |
| *Billing account required* | Link billing to the project in the Cloud Console → Billing |
| Build fails at `npm ci` | Run `npm install` in `frontend` once, so `package-lock.json` is current, then deploy again |
| `/api/ai/status` says `connected: false` | The secret is missing or empty: check `gcloud secrets versions access latest --secret gemini-api-key` prints your key, then deploy again |
| Gemini answers with a quota or model error | Check the key works in AI Studio. To change the model, set `GEMINI_MODEL` in `backend\.env` locally, or `--set-env-vars GEMINI_MODEL=...` on Cloud Run |
| *Permission denied* on `--allow-unauthenticated` | Your organisation blocks public services; use a personal Google account project |

## What to submit

* **Live URL:** the Cloud Run address from Step 4.
* **AI used:** Gemini (Google Gen AI SDK) for function calling with 15 tools, structured output, vision (bills,
  logbooks, nameplates) and audio (voice questions).
* **Google Cloud:** Cloud Run, Cloud Build, Artifact Registry, Secret Manager.
* **Code:** this repository. `README.md` has the product overview and local setup instructions.
