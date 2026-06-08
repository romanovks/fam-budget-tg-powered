import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.main import scheduled_digest, telegram_webhook
from app.models import Person


class FakeTelegramClient:
    messages: list[tuple[int, str]] = []

    def __init__(self, token: str) -> None:
        self.token = token

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class PartiallyFailingTelegramClient(FakeTelegramClient):
    async def send_message(self, chat_id: int, text: str) -> None:
        if chat_id == 202:
            raise RuntimeError("bot was blocked by the user")
        await super().send_message(chat_id, text)


class FakeDigestProcessor:
    def __init__(self) -> None:
        self.report_calls: list[tuple[str, bool]] = []

    def report_summary(self, period: str, *, previous: bool = False) -> str:
        self.report_calls.append((period, previous))
        return f"{period} report"

    def recipient_chat_ids(self) -> list[int]:
        return [101, 202]


class FakeRequest:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def json(self) -> dict:
        return self._payload


class FakeWebhookProcessor:
    def __init__(self) -> None:
        self.written = False

    def person_from_telegram_id(self, telegram_id: int) -> Person | None:
        return Person.KONSTANTIN if telegram_id == 101 else None

    def parse_text(self, text: str, person: Person) -> object:
        return object()

    def handle_limit_text(self, text: str, person: Person) -> str | None:
        return None

    async def normalize(self, parse_result: object, person: Person) -> list[object]:
        return [object()]

    def write_and_summarize(self, **kwargs) -> str:
        self.written = True
        return "Внесено: 1 транзакц."

    def already_processed(self, update_id: int) -> bool:
        return False

    def limit_alerts(self) -> list[str]:
        return ["Лимит достигнут: Groceries"]

    def recipient_chat_ids(self) -> list[int]:
        return [101, 202]


def test_scheduled_digest_sends_previous_week_report_to_both_recipients(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTelegramClient.messages = []
    monkeypatch.setattr("app.main.TelegramClient", FakeTelegramClient)
    processor = FakeDigestProcessor()
    settings = SimpleNamespace(tasks_secret="tasks-secret", telegram_bot_token="telegram-token")

    result = asyncio.run(
        scheduled_digest(
            "weekly",
            x_tasks_secret="tasks-secret",
            settings=settings,
            processor=processor,
        )
    )

    assert result == {"ok": True}
    assert processor.report_calls == [("week", True)]
    assert FakeTelegramClient.messages == [(101, "week report"), (202, "week report")]


def test_scheduled_digest_rejects_wrong_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.main.TelegramClient", FakeTelegramClient)
    settings = SimpleNamespace(tasks_secret="tasks-secret", telegram_bot_token="telegram-token")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            scheduled_digest(
                "weekly",
                x_tasks_secret="wrong",
                settings=settings,
                processor=FakeDigestProcessor(),
            )
        )

    assert exc.value.status_code == 401


def test_scheduled_digest_continues_when_one_recipient_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    PartiallyFailingTelegramClient.messages = []
    monkeypatch.setattr("app.main.TelegramClient", PartiallyFailingTelegramClient)
    settings = SimpleNamespace(tasks_secret="tasks-secret", telegram_bot_token="telegram-token")

    result = asyncio.run(
        scheduled_digest(
            "weekly",
            x_tasks_secret="tasks-secret",
            settings=settings,
            processor=FakeDigestProcessor(),
        )
    )

    assert result == {"ok": True}
    assert PartiallyFailingTelegramClient.messages == [(101, "week report")]


def test_webhook_sends_transaction_summary_and_limit_alerts_to_recipients(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTelegramClient.messages = []
    monkeypatch.setattr("app.main.TelegramClient", FakeTelegramClient)
    settings = SimpleNamespace(telegram_bot_token="telegram-token", telegram_webhook_secret="webhook-secret")
    processor = FakeWebhookProcessor()
    request = FakeRequest(
        {
            "update_id": 123,
            "message": {
                "chat": {"id": 999},
                "from": {"id": 101},
                "text": "купил продукты за 120 злотых",
            },
        }
    )

    result = asyncio.run(
        telegram_webhook(
            request,
            x_telegram_bot_api_secret_token="webhook-secret",
            settings=settings,
            processor=processor,
        )
    )

    assert result == {"ok": True}
    assert processor.written
    assert FakeTelegramClient.messages == [
        (999, "Внесено: 1 транзакц."),
        (101, "Лимит достигнут: Groceries"),
        (202, "Лимит достигнут: Groceries"),
    ]
