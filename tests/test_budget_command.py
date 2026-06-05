from types import SimpleNamespace

from app.main import is_budget_request
from app.processor import BudgetProcessor


class FakeSheetsClient:
    def read_dashboard(self) -> dict[str, str]:
        return {
            "Total Income": "20,000.00",
            "Total Expenses": "4,468.24",
            "Net Savings": "15,531.76",
        }


def test_budget_request_matches_command_and_phrase() -> None:
    assert is_budget_request("/budget")
    assert is_budget_request("покажи текущий бюджет")
    assert is_budget_request("поточний бюджет")


def test_current_budget_summary_uses_dashboard_values() -> None:
    processor = BudgetProcessor(
        settings=SimpleNamespace(),
        openai_client=SimpleNamespace(),
        sheets_client=FakeSheetsClient(),
        nbp_client=SimpleNamespace(),
    )

    assert processor.current_budget_summary() == (
        "Текущий бюджет:\n"
        "Доходы: 20,000.00 PLN\n"
        "Расходы: 4,468.24 PLN\n"
        "Баланс: 15,531.76 PLN"
    )
