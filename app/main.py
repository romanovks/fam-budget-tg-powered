from fastapi import Depends, FastAPI, Header, HTTPException, Request
from openai import OpenAIError

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


@app.post("/tasks/digest/{period}")
async def scheduled_digest(
    period: str,
    x_tasks_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    processor: BudgetProcessor = Depends(get_processor),
) -> dict[str, bool]:
    if not settings.tasks_secret or x_tasks_secret != settings.tasks_secret:
        raise HTTPException(status_code=401, detail="Invalid tasks secret")
    if period not in {"weekly", "monthly"}:
        raise HTTPException(status_code=404, detail="Unknown digest period")

    telegram = TelegramClient(settings.telegram_bot_token)
    report_period = "week" if period == "weekly" else "month"
    text = processor.report_summary(report_period, previous=True)
    await send_to_recipients(telegram, processor, text)
    return {"ok": True}


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

    if is_budget_request(message.get("text", "")):
        await telegram.send_message(chat_id, processor.current_budget_summary())
        return {"ok": True}

    if report_period := report_request_period(message.get("text", "")):
        await telegram.send_message(chat_id, processor.report_summary(report_period, previous=False))
        return {"ok": True}

    if limit_response := processor.handle_limit_text(message.get("text", ""), person):
        await telegram.send_message(chat_id, limit_response)
        return {"ok": True}

    if processor.already_processed(update_id):
        await telegram.send_message(chat_id, "Это сообщение уже обработано, пропускаю дубль.")
        return {"ok": True}

    try:
        if message.get("text", "").startswith("/start"):
            await telegram.send_message(
                chat_id,
                "Я готов вести семейный бюджет. Пиши расходы текстом, голосом или присылай фото чека. /budget покажет текущий бюджет.",
            )
            return {"ok": True}
        if is_test_message(message.get("text", "")):
            await telegram.send_message(chat_id, "Тест принят: бот отвечает, в таблицу ничего не записал.")
            return {"ok": True}
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
        for alert in processor.limit_alerts():
            await send_to_recipients(telegram, processor, alert)
    except Exception as exc:
        await telegram.send_message(chat_id, user_facing_error(exc))
    return {"ok": True}


def user_facing_error(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, OpenAIError) or "insufficient_quota" in message:
        return (
            "Не смог обработать сообщение: у OpenAI API key нет доступной квоты или не включён billing. "
            "Проверь OpenAI Platform -> Billing и лимиты проекта, потом повтори сообщение."
        )
    if "PERMISSION_DENIED" in message or "403" in message:
        return (
            "Не смог записать в Google Sheet: похоже, у service account нет доступа. "
            "Проверь, что таблица расшарена на service account с правами Editor."
        )
    return f"Не смог обработать сообщение. Ошибка: {message[:300]}"


def is_test_message(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized == "test" or normalized == "тест" or normalized.startswith("test ") or normalized.startswith("тест ")


def is_budget_request(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {
        "/budget",
        "/balance",
        "budget",
        "balance",
        "баланс",
        "покажи баланс",
        "покажи бюджет",
        "покажи текущий бюджет",
        "текущий бюджет",
        "текущий семейный бюджет",
        "поточний бюджет",
        "покажи поточний бюджет",
        "покажи поточний баланс",
    }


def report_request_period(text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized in {"/week", "week", "покажи неделю", "отчет за неделю", "звіт за тиждень"}:
        return "week"
    if normalized in {"/month", "month", "покажи месяц", "отчет за месяц", "звіт за місяць"}:
        return "month"
    if "отчет" in normalized or "звіт" in normalized or "репорт" in normalized:
        if "недел" in normalized or "тиж" in normalized:
            return "week"
        if "месяц" in normalized or "міся" in normalized:
            return "month"
    return None


async def send_to_recipients(telegram: TelegramClient, processor: BudgetProcessor, text: str) -> None:
    for chat_id in processor.recipient_chat_ids():
        await telegram.send_message(chat_id, text)


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
