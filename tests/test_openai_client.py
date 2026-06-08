from app.config import Settings
from app.models import Person
from app.openai_client import BudgetOpenAIClient


def test_parse_result_coerces_loose_llm_json() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="test",
        TELEGRAM_WEBHOOK_SECRET="test",
        OPENAI_API_KEY="test",
        SPREADSHEET_ID="sheet",
        KONSTANTIN_TELEGRAM_ID=1,
        SVITLANA_TELEGRAM_ID=2,
    )
    client = BudgetOpenAIClient(settings)

    result = client._parse_result(
        content='{"transactions":[{"person":"Unknown","type":"расход","category":"Other","subcategory":"Uncategorized","amount":1,"currency":"злотый","payment_owner":"Family","family_personal":"Personal","flags":["Needs Review"]}]}',
        current_date="2026-06-03",
        person=Person.KONSTANTIN,
        default_account="Family Card",
        original_text="тест расход 1 злотый",
    )

    tx = result.transactions[0]
    assert result.summary == "тест расход 1 злотый"
    assert tx.person == "Konstantin"
    assert tx.currency == "PLN"
    assert tx.payment_owner == "Konstantin"
    assert tx.family_personal == "Konstantin Personal"
    assert tx.review_status == "OK"


def test_parse_result_infers_known_merchant_from_text() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="test",
        TELEGRAM_WEBHOOK_SECRET="test",
        OPENAI_API_KEY="test",
        SPREADSHEET_ID="sheet",
        KONSTANTIN_TELEGRAM_ID=1,
        SVITLANA_TELEGRAM_ID=2,
    )
    client = BudgetOpenAIClient(settings)

    result = client._parse_result(
        content='{"transactions":[{"type":"Expense","category":"Other","subcategory":"Uncategorized","amount":78,"currency":"PLN"}]}',
        current_date="2026-06-08",
        person=Person.KONSTANTIN,
        default_account="Family Card",
        original_text="Żabka стики iqos 78 PLN",
    )

    assert result.transactions[0].merchant == "Żabka"
