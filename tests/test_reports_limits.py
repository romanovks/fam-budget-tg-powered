from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.models import Person
from app.processor import BudgetProcessor
from app.sheets import BudgetLimit, SheetTransaction


class FakeSheetsClient:
    def __init__(self) -> None:
        today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
        self.transactions = [
            SheetTransaction("1", today, "Konstantin", "Expense", "Groceries", "Supermarket", 120.0),
            SheetTransaction("2", today, "Svitlana", "Expense", "Sport", "Gym", 80.0),
            SheetTransaction("3", today, "Konstantin", "Income", "Salary", "Main salary", 1000.0),
        ]
        self.limits = [
            BudgetLimit(2, "LIM-1", "Category", "Groceries", "", "Monthly", 100.0, [80, 100], "Both", True, "Konstantin", "", "", ""),
        ]
        self.created_limits = []
        self.alert_keys = []
        self.deactivated_rows = []

    def read_transactions(self):
        return self.transactions

    def read_dashboard(self):
        return {"Net Savings": "15,531.76"}

    def read_limits(self):
        return self.limits

    def append_limit(self, **kwargs):
        self.created_limits.append(kwargs)

    def update_limit_alert_key(self, row_number, alert_key):
        self.alert_keys.append((row_number, alert_key))

    def deactivate_limit(self, row_number):
        self.deactivated_rows.append(row_number)


def make_processor(fake_sheets: FakeSheetsClient) -> BudgetProcessor:
    return BudgetProcessor(
        settings=SimpleNamespace(
            timezone="Europe/Warsaw",
            konstantin_telegram_id=1,
            svitlana_telegram_id=2,
            default_account_konstantin="Family Card",
            default_account_svitlana="Svitlana Card",
        ),
        openai_client=SimpleNamespace(),
        sheets_client=fake_sheets,
        nbp_client=SimpleNamespace(),
    )


def test_report_summary_includes_totals_and_top_categories() -> None:
    processor = make_processor(FakeSheetsClient())

    report = processor.report_summary("month")

    assert "Расходы: 200.00 PLN" in report
    assert "Доходы: 1,000.00 PLN" in report
    assert "1. Groceries: 120.00 PLN" in report


def test_category_limit_command_creates_monthly_limit() -> None:
    fake_sheets = FakeSheetsClient()
    processor = make_processor(fake_sheets)

    response = processor.handle_limit_text("установи лимит на продукты 2500 злотых в месяц", Person.KONSTANTIN)

    assert "Лимит установлен: Groceries 2,500.00 PLN" in response
    assert fake_sheets.created_limits[0]["category"] == "Groceries"
    assert fake_sheets.created_limits[0]["amount_pln"] == 2500.0


def test_limit_alert_fires_once_when_threshold_is_reached() -> None:
    fake_sheets = FakeSheetsClient()
    processor = make_processor(fake_sheets)

    alerts = processor.limit_alerts()

    assert len(alerts) == 1
    assert "Лимит достигнут: Groceries" in alerts[0]
    assert fake_sheets.alert_keys[0][0] == 2


def test_balance_alert_command_creates_shared_alert() -> None:
    fake_sheets = FakeSheetsClient()
    processor = make_processor(fake_sheets)

    response = processor.handle_limit_text("/alert balance below 10000 PLN", Person.SVITLANA)

    assert "Балансовый алерт установлен" in response
    assert fake_sheets.created_limits[0]["scope"] == "Balance"
    assert fake_sheets.created_limits[0]["recipients"] == "Both"
    assert fake_sheets.created_limits[0]["amount_pln"] == 10000.0


def test_delete_limit_deactivates_matching_category_limit() -> None:
    fake_sheets = FakeSheetsClient()
    processor = make_processor(fake_sheets)

    response = processor.handle_limit_text("/delete_limit продукты", Person.KONSTANTIN)

    assert response == "Лимит Groceries отключен."
    assert fake_sheets.deactivated_rows == [2]
