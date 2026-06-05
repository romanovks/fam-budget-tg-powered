from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.currency import NbpClient
from app.models import Currency, NormalizedTransaction, ParseResult, Person, ReviewStatus
from app.openai_client import BudgetOpenAIClient
from app.sheets import SheetsClient
from app.taxonomy import normalize_account, normalize_category


class BudgetProcessor:
    def __init__(
        self,
        settings: Settings,
        openai_client: BudgetOpenAIClient,
        sheets_client: SheetsClient,
        nbp_client: NbpClient,
    ) -> None:
        self._settings = settings
        self._openai = openai_client
        self._sheets = sheets_client
        self._nbp = nbp_client

    def person_from_telegram_id(self, telegram_id: int) -> Person | None:
        if telegram_id == self._settings.konstantin_telegram_id:
            return Person.KONSTANTIN
        if telegram_id == self._settings.svitlana_telegram_id:
            return Person.SVITLANA
        return None

    def default_account(self, person: Person) -> str:
        if person == Person.SVITLANA:
            return self._settings.default_account_svitlana
        return self._settings.default_account_konstantin

    def parse_text(self, text: str, person: Person) -> ParseResult:
        return self._openai.parse_text(
            text=text,
            person=person,
            current_date=self.current_date(),
            default_account=self.default_account(person),
        )

    async def normalize(self, parse_result: ParseResult, person: Person) -> list[NormalizedTransaction]:
        normalized = []
        for tx in parse_result.transactions:
            category, subcategory, category_changed = normalize_category(tx.type, tx.category, tx.subcategory)
            account, account_changed = normalize_account(tx.account, self.default_account(person))
            rate = await self._nbp.get_rate(tx.currency, tx.date)
            notes = tx.notes
            amount_pln = tx.amount
            exchange_rate = None
            exchange_source = None
            if tx.currency != Currency.PLN:
                amount_pln = round(tx.amount * rate.pln, 2)
                exchange_rate = rate.pln
                exchange_source = f"NBP {rate.table}, effective {rate.effective_date}"
                notes = (
                    f"{notes} Original: {tx.amount:g} {tx.currency.value}. "
                    f"Converted with {exchange_source}, {tx.currency.value}/PLN {rate.pln}."
                ).strip()
            if category_changed:
                notes = f"{notes} Category normalized from {tx.category} / {tx.subcategory}.".strip()
                tx.review_status = ReviewStatus.NEEDS_REVIEW
            if account_changed:
                notes = f"{notes} Account normalized from {tx.account} to {account}.".strip()
                tx.review_status = ReviewStatus.NEEDS_REVIEW

            normalized.append(
                NormalizedTransaction(
                    **tx.model_dump(exclude={"amount", "currency", "category", "subcategory", "account", "notes"}),
                    amount=amount_pln,
                    currency=Currency.PLN,
                    category=category,
                    subcategory=subcategory,
                    account=account,
                    notes=notes,
                    original_amount=tx.amount,
                    original_currency=tx.currency,
                    exchange_rate=exchange_rate,
                    exchange_rate_source=exchange_source,
                )
            )
        return normalized

    def write_and_summarize(
        self,
        *,
        update_id: int,
        person: Person,
        raw_text: str,
        parse_result: ParseResult,
        transactions: list[NormalizedTransaction],
    ) -> str:
        transaction_ids = [self.transaction_id(update_id, index) for index, _ in enumerate(transactions, start=1)]
        self._sheets.append_raw_input(
            update_id=update_id,
            person=person,
            raw_text=raw_text,
            parse_result=parse_result,
            transaction_ids=transaction_ids,
        )
        self._sheets.append_transactions(transactions, transaction_ids)
        dashboard = self._sheets.read_dashboard()
        lines = [f"Внесено: {len(transactions)} транзакц."]
        for tx in transactions:
            lines.append(f"- {tx.merchant}: {tx.amount:,.2f} PLN, {tx.category} / {tx.subcategory}")
        if dashboard.get("Net Savings"):
            lines.append(f"Баланс: {dashboard['Net Savings']} PLN")
        return "\n".join(lines)

    def current_budget_summary(self) -> str:
        dashboard = self._sheets.read_dashboard()
        income = dashboard.get("Total Income", "n/a")
        expenses = dashboard.get("Total Expenses", "n/a")
        balance = dashboard.get("Net Savings", "n/a")
        return "\n".join(
            [
                "Текущий бюджет:",
                f"Доходы: {income} PLN",
                f"Расходы: {expenses} PLN",
                f"Баланс: {balance} PLN",
            ]
        )

    def already_processed(self, update_id: int) -> bool:
        return self._sheets.already_processed(update_id)

    def current_date(self) -> str:
        return datetime.now(ZoneInfo(self._settings.timezone)).strftime("%Y-%m-%d")

    def transaction_id(self, update_id: int, index: int) -> str:
        return f"TG-{update_id}-{index:02d}"
