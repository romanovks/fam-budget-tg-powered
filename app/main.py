from fastapi import Depends, FastAPI, Header, HTTPException, Request

from app.audio import convert_telegram_voice_to_mp3
from app.config import Settings, get_settings
from app.currency import NbpClient
from app.models import ParseResult
from app.openai_client import BudgetOpenAIClient
from app.processor import BudgetProcessor
from app.sheets import SheetsClient
from app.telegram import TelegramClient

app = FastAPI(title="Family Budget Telegram Bot")


def get_processor(settings: Settings = Depends(get_settings)) -> BudgetProcessor:
    return BudgetProcessor(
        settings=settings,
        openai_client=BudgetOpenAIClient(settings),
        sheets_client=SheetsClient(settings.google_service_account_json, settings.spreadsheet_id, settings.timezone),
        nbp_client=NbpClient(),
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    processor: BudgetProcessor = Depends(get_processor),
) -> dict[str, bool]:
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    update = await request.json()
    update_id = int(update["update_id"])
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = int(message["chat"]["id"])
    sender_id = int(message["from"]["id"])
    telegram = TelegramClient(settings.telegram_bot_token)
    person = processor.person_from_telegram_id(sender_id)
    if person is None:
        await telegram.send_message(chat_id, "Я знаю только Konstantin и Svitlana. Добавь этот Telegram user id в настройки.")
        return {"ok": True}

    if processor.already_processed(update_id):
        await telegram.send_message(chat_id, "Это сообщение уже обработано, пропускаю дубль.")
        return {"ok": True}

    try:
        text, parse_result = await parse_message(message, telegram, settings, processor, person)
        transactions = await processor.normalize(parse_result, person)
        response_text = processor.write_and_summarize(
            update_id=update_id,
            person=person,
            raw_text=text,
            parse_result=parse_result,
            transactions=transactions,
        )
        await telegram.send_message(chat_id, response_text)
    except Exception as exc:
        await telegram.send_message(chat_id, f"Не смог обработать сообщение. Ошибка: {exc}")
    return {"ok": True}


async def parse_message(
    message: dict,
    telegram: TelegramClient,
    settings: Settings,
    processor: BudgetProcessor,
    person,
) -> tuple[str, ParseResult]:
    if message.get("text"):
        text = message["text"]
        return text, processor.parse_text(text, person)

    caption = message.get("caption") or ""
    openai_client = BudgetOpenAIClient(settings)

    if voice := message.get("voice"):
        source = await telegram.download_file(voice["file_id"], ".oga")
        mp3 = convert_telegram_voice_to_mp3(source)
        transcript = openai_client.transcribe_audio(mp3)
        text = f"{caption}\n{transcript}".strip()
        return text, processor.parse_text(text, person)

    if photos := message.get("photo"):
        largest = photos[-1]
        image_path = await telegram.download_file(largest["file_id"], ".jpg")
        parsed = openai_client.parse_image(
            image_path=image_path,
            mime_type="image/jpeg",
            caption=caption,
            person=person,
            current_date=processor.current_date(),
            default_account=processor.default_account(person),
        )
        raw_text = caption or f"Photo receipt: {parsed.summary}"
        return raw_text, parsed

    raise ValueError("Поддерживаются текст, voice message и фото.")
