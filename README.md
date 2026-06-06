# Family Budget Telegram Bot

Telegram bot that accepts family-budget messages from Konstantin and Svitlana, parses them with OpenAI, normalizes currencies to PLN, writes rows to Google Sheets, and returns the current balance back to Telegram.

Target spreadsheet:

https://docs.google.com/spreadsheets/d/12l-A4RKoQ6ZybkQt1k08LIx3mxJPuMDoiFbBx4SQp7U/edit?gid=106#gid=106

## Flow

```text
Telegram chat
  -> Cloud Run webhook
  -> OpenAI transcription / vision / structured parsing
  -> validation + NBP currency conversion
  -> Google Sheets Raw Input + Transactions
  -> Dashboard balance back to Telegram
```

## Bot Commands

Recommended BotFather commands:

```text
start - проверить, что бот жив и готов записывать расходы
budget - показать текущий бюджет и баланс
week - показать отчет за текущую неделю
month - показать отчет за текущий месяц
limits - показать активные лимиты и алерты
```

The same budget summary also works with plain messages like `покажи текущий бюджет`, `покажи баланс`, or `поточний бюджет`.

Useful commands:

```text
/week
/month
/limit продукты 2500 PLN month
/limit спорт 600 PLN week
/limits
/delete_limit продукты
/alert balance below 10000 PLN
```

## What I Need From You

### 1. Telegram bot token

1. Open Telegram.
2. Message `@BotFather`.
3. Run `/newbot`.
4. Choose a bot name and username.
5. Copy the token.

Send it in this form:

```text
TELEGRAM_BOT_TOKEN=123456:ABC...
```

### 2. Telegram user ids

For both you and Svitlana:

1. Open Telegram.
2. Message `@userinfobot`.
3. Copy the numeric `Id`.

Send them in this form:

```text
KONSTANTIN_TELEGRAM_ID=123456789
SVITLANA_TELEGRAM_ID=987654321
```

### 3. OpenAI API key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key.
3. Copy it once.

Send it in this form:

```text
OPENAI_API_KEY=sk-...
```

### 4. Google service account

1. Go to Google Cloud Console.
2. Create or select a project.
3. Enable Google Sheets API.
4. Go to IAM & Admin -> Service Accounts.
5. Create a service account.
6. Do not create a JSON key if your organization blocks keys.
7. Share the Google Sheet with the service account email, usually like:

```text
something@project-id.iam.gserviceaccount.com
```

Give it Editor access.

On Cloud Run, attach this service account to the service. The app will use Application Default Credentials automatically, so `GOOGLE_SERVICE_ACCOUNT_JSON` is not needed.

For local development only, either run:

```bash
gcloud auth application-default login
```

or, if your organization allows keys, paste JSON as one line or base64 encode it. Safer key form:

```bash
base64 -i /path/to/service-account.json
```

Send the output as:

```text
GOOGLE_SERVICE_ACCOUNT_JSON=base64-output-here
```

### 5. Webhook secret

Generate any long random string. Example:

```bash
openssl rand -hex 32
```

Send it as:

```text
TELEGRAM_WEBHOOK_SECRET=...
```

## Environment

Create `.env` locally:

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TASKS_SECRET=
OPENAI_API_KEY=
# Optional. Leave empty on Cloud Run or when using gcloud auth application-default login.
GOOGLE_SERVICE_ACCOUNT_JSON=
SPREADSHEET_ID=12l-A4RKoQ6ZybkQt1k08LIx3mxJPuMDoiFbBx4SQp7U
KONSTANTIN_TELEGRAM_ID=
SVITLANA_TELEGRAM_ID=
OPENAI_PARSE_MODEL=gpt-4.1-mini
OPENAI_VISION_MODEL=gpt-4.1-mini
OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
DEFAULT_ACCOUNT_KONSTANTIN=Family Card
DEFAULT_ACCOUNT_SVITLANA=Svitlana Card
TIMEZONE=Europe/Warsaw
```

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8080
```

## Cloud Run Deployment Plan

Use Cloud Run with `min instances = 0` for near-free webhook hosting.

### Deploy with gcloud

Set local shell variables. Do not commit these values:

```bash
export PROJECT_ID="your-google-cloud-project-id"
export REGION="europe-west1"
export SERVICE="fam-budget-tg-powered"
export SERVICE_ACCOUNT_EMAIL="tg-fin-helper@project-af60215d-0436-4b7f-b01.iam.gserviceaccount.com"
export SPREADSHEET_ID="12l-A4RKoQ6ZybkQt1k08LIx3mxJPuMDoiFbBx4SQp7U"
```

Enable APIs:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com sheets.googleapis.com --project "$PROJECT_ID"
```

Create secrets. Paste the secret values when prompted:

```bash
printf %s "PASTE_NEW_TELEGRAM_BOT_TOKEN" | gcloud secrets create telegram-bot-token --data-file=- --project "$PROJECT_ID"
printf %s "PASTE_NEW_OPENAI_API_KEY" | gcloud secrets create openai-api-key --data-file=- --project "$PROJECT_ID"
printf %s "PASTE_WEBHOOK_SECRET" | gcloud secrets create telegram-webhook-secret --data-file=- --project "$PROJECT_ID"
openssl rand -hex 32 | gcloud secrets create tasks-secret --data-file=- --project "$PROJECT_ID"
```

Allow the Cloud Run service account to read these secrets:

```bash
gcloud secrets add-iam-policy-binding telegram-bot-token --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role "roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
gcloud secrets add-iam-policy-binding openai-api-key --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role "roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
gcloud secrets add-iam-policy-binding telegram-webhook-secret --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role "roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
gcloud secrets add-iam-policy-binding tasks-secret --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role "roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
```

Deploy from the repo root:

```bash
gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --service-account "$SERVICE_ACCOUNT_EMAIL" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --memory 512Mi \
  --set-env-vars "SPREADSHEET_ID=$SPREADSHEET_ID,KONSTANTIN_TELEGRAM_ID=433497646,SVITLANA_TELEGRAM_ID=409566099,TIMEZONE=Europe/Warsaw,DEFAULT_ACCOUNT_KONSTANTIN=Family Card,DEFAULT_ACCOUNT_SVITLANA=Svitlana Card" \
  --set-secrets "TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,OPENAI_API_KEY=openai-api-key:latest,TELEGRAM_WEBHOOK_SECRET=telegram-webhook-secret:latest,TASKS_SECRET=tasks-secret:latest"
```

After deployment, set the Telegram webhook:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://YOUR-CLOUD-RUN-URL/telegram/webhook",
    "secret_token": "YOUR_TELEGRAM_WEBHOOK_SECRET",
    "allowed_updates": ["message", "edited_message"]
  }'
```

## Automatic Deploys from GitHub Actions

The repo includes `.github/workflows/deploy-cloud-run.yml`. Every push to `master` runs tests and deploys the bot to Cloud Run.

GitHub does not store Telegram or OpenAI secrets. Those stay in Google Secret Manager. GitHub Actions authenticates to Google Cloud through Workload Identity Federation.

### One-time GCP setup

Run this once in Cloud Shell:

```bash
export PROJECT_ID="project-af60215d-0436-4b7f-b01"
export PROJECT_NUMBER="702807059402"
export REGION="europe-west1"
export REPO="romanovks/fam-budget-tg-powered"
export POOL_ID="github-actions"
export PROVIDER_ID="github-actions"
export DEPLOYER_SA_NAME="github-actions-deployer"
export DEPLOYER_SA="$DEPLOYER_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
export RUNTIME_SA="tg-fin-helper@$PROJECT_ID.iam.gserviceaccount.com"
```

Enable APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  --project "$PROJECT_ID"
```

Create a deployer service account:

```bash
gcloud iam service-accounts create "$DEPLOYER_SA_NAME" \
  --project "$PROJECT_ID" \
  --display-name "GitHub Actions Cloud Run deployer"
```

Grant deploy permissions:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$DEPLOYER_SA" \
  --role "roles/run.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$DEPLOYER_SA" \
  --role "roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$DEPLOYER_SA" \
  --role "roles/artifactregistry.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$DEPLOYER_SA" \
  --role "roles/storage.admin"

gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --project "$PROJECT_ID" \
  --member "serviceAccount:$DEPLOYER_SA" \
  --role "roles/iam.serviceAccountUser"
```

Allow the deployer to reference the existing Secret Manager secrets during deploy:

```bash
for SECRET in telegram-bot-token openai-api-key telegram-webhook-secret tasks-secret; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project "$PROJECT_ID" \
    --member "serviceAccount:$DEPLOYER_SA" \
    --role "roles/secretmanager.secretAccessor"
done
```

Create the GitHub OIDC pool and provider:

```bash
gcloud iam workload-identity-pools create "$POOL_ID" \
  --project "$PROJECT_ID" \
  --location "global" \
  --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project "$PROJECT_ID" \
  --location "global" \
  --workload-identity-pool "$POOL_ID" \
  --display-name "GitHub Actions provider" \
  --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition "assertion.repository == '$REPO' && assertion.ref == 'refs/heads/master'"
```

Allow only this GitHub repo to impersonate the deployer service account:

```bash
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA" \
  --project "$PROJECT_ID" \
  --role "roles/iam.workloadIdentityUser" \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/$REPO"
```

Expected provider value used by the workflow:

```text
projects/702807059402/locations/global/workloadIdentityPools/github-actions/providers/github-actions
```

The repo also includes `.github/workflows/scheduled-digests.yml`:

- every Monday at `06:00 UTC`, it asks the bot to send the previous-week digest to both private Telegram chats
- every first day of the month at `06:10 UTC`, it asks the bot to send the previous-month digest to both private Telegram chats
- manual runs are available from GitHub Actions with `weekly` or `monthly`

After this setup, pushing to `master` is enough:

```bash
git push origin HEAD:master
```

## Notes

- The bot writes the original message to `Raw Input` first.
- Then it writes normalized rows to `Transactions`.
- `Amount` is always stored in PLN.
- Original currency, source amount, and NBP rate are stored in `Notes`.
- Telegram voice messages are converted with `ffmpeg` before OpenAI transcription because Telegram uses OGG/Opus.
