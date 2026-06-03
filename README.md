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

### 4. Google service account JSON

1. Go to Google Cloud Console.
2. Create or select a project.
3. Enable Google Sheets API.
4. Go to IAM & Admin -> Service Accounts.
5. Create a service account.
6. Open it -> Keys -> Add key -> Create new key -> JSON.
7. Download the JSON file.
8. Share the Google Sheet with the service account email, usually like:

```text
something@project-id.iam.gserviceaccount.com
```

Give it Editor access.

For local `.env`, the JSON can be pasted as one line or base64 encoded. Safer form:

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
