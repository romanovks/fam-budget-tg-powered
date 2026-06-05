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
```

The same budget summary also works with plain messages like `покажи текущий бюджет`, `покажи баланс`, or `поточний бюджет`.

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
```

Allow the Cloud Run service account to read these secrets:

```bash
gcloud secrets add-iam-policy-binding telegram-bot-token --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role "roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
gcloud secrets add-iam-policy-binding openai-api-key --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role "roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
gcloud secrets add-iam-policy-binding telegram-webhook-secret --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role "roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
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
  --set-secrets "TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,OPENAI_API_KEY=openai-api-key:latest,TELEGRAM_WEBHOOK_SECRET=telegram-webhook-secret:latest"
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

## Notes

- The bot writes the original message to `Raw Input` first.
- Then it writes normalized rows to `Transactions`.
- `Amount` is always stored in PLN.
- Original currency, source amount, and NBP rate are stored in `Notes`.
- Telegram voice messages are converted with `ffmpeg` before OpenAI transcription because Telegram uses OGG/Opus.
