import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.currency import NbpClient
from app.models import Currency, NormalizedTransaction, ParseResult, Person, ReviewStatus
from app.openai_client import BudgetOpenAIClient
from app.sheets import BudgetLimit, SheetsClient, SheetTransaction
from app.taxonomy import normalize_account, normalize_category


CATEGORY_ALIASES = {
    "groceries": "Groceries",
    "grocery": "Groceries",
    "products": "Groceries",
    "food": "Groceries",
    "продукты": "Groceries",
    "продукти": "Groceries",
    "еда": "Groceries",
    "їжа": "Groceries",
    "супермаркет": "Groceries",
    "carrefour": "Groceries",
    "карефур": "Groceries",
    "sport": "Sport",
    "спорт": "Sport",
    "gym": "Sport",
    "зал": "Sport",
    "restaurants": "Restaurants",
    "restaurant": "Restaurants",
    "рестораны": "Restaurants",
    "ресторани": "Restaurants",
    "кафе": "Restaurants",
    "mcdonalds": "Restaurants",
    "макдональдс": "Restaurants",
    "transport": "Transport",
    "транспорт": "Transport",
    "parking": "Transport",
    "парковка": "Transport",
    "housing": "Housing",
    "rent": "Housing",
    "квартира": "Housing",
    "аренда": "Housing",
    "оренда": "Housing",
    "коммуналка": "Housing",
    "комуналка": "Housing",
    "health": "Health",
    "здоровье": "Health",
    "здоров'я": "Health",
    "shopping": "Shopping",
    "шопинг": "Shopping",
    "покупки": "Shopping",
    "subscriptions": "Subscriptions",
    "подписки": "Subscriptions",
    "підписки": "Subscriptions",
    "entertainment": "Entertainment",
    "развлечения": "Entertainment",
    "розваги": "Entertainment",
}


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

    def limit_alerts(self) -> list[str]:
        transactions = self._sheets.read_transactions()
        dashboard = self._sheets.read_dashboard()
        alerts = []
        for limit in self._sheets.read_limits():
            if not limit.active:
                continue
            if limit.scope == "Balance":
                message = self._balance_alert(limit, dashboard)
            else:
                message = self._category_limit_alert(limit, transactions)
            if message:
                alerts.append(message)
        return alerts

    def report_summary(self, period: str, *, previous: bool = False) -> str:
        start, end, title = self._period_bounds(period, previous=previous)
        transactions = [
            tx for tx in self._sheets.read_transactions()
            if start <= tx.date <= end
        ]
        expenses = [tx for tx in transactions if tx.tx_type == "Expense"]
        incomes = [tx for tx in transactions if tx.tx_type in {"Income", "Refund"}]
        total_expenses = sum(tx.amount for tx in expenses)
        total_income = sum(tx.amount for tx in incomes)
        dashboard = self._sheets.read_dashboard()

        by_category: dict[str, float] = {}
        for tx in expenses:
            by_category[tx.category] = by_category.get(tx.category, 0) + tx.amount

        lines = [
            f"Отчет: {title}",
            f"Расходы: {total_expenses:,.2f} PLN",
            f"Доходы: {total_income:,.2f} PLN",
        ]
        if dashboard.get("Net Savings"):
            lines.append(f"Текущий баланс: {dashboard['Net Savings']} PLN")

        lines.append("")
        lines.append("Топ-5 категорий:")
        top_categories = sorted(by_category.items(), key=lambda item: item[1], reverse=True)[:5]
        if top_categories:
            for index, (category, amount) in enumerate(top_categories, start=1):
                lines.append(f"{index}. {category}: {amount:,.2f} PLN")
        else:
            lines.append("Пока нет расходов за этот период.")

        limit_lines = self._limit_report_lines(period, start, end)
        if limit_lines:
            lines.append("")
            lines.append("Лимиты:")
            lines.extend(limit_lines)
        return "\n".join(lines)

    def handle_limit_text(self, text: str, person: Person) -> str | None:
        normalized = text.strip()
        lower = normalized.lower()
        if lower == "/limits" or lower in {"лимиты", "покажи лимиты", "покажи ліміти", "ліміти"}:
            return self.limits_summary()
        if lower.startswith("/delete_limit") or lower.startswith("/remove_limit"):
            category_text = normalized.split(maxsplit=1)[1] if len(normalized.split(maxsplit=1)) > 1 else ""
            return self.delete_limit(category_text)
        if lower.startswith("/alert") or ("баланс" in lower and any(word in lower for word in ("ниже", "нижче", "меньше", "менше", "опуст"))):
            return self.create_balance_alert(normalized, person)
        if self._is_limit_create_request(lower):
            return self.create_category_limit(normalized, person)
        return None

    def create_category_limit(self, text: str, person: Person) -> str:
        amount = self._extract_amount(text)
        if amount is None:
            return "Не понял сумму лимита. Пример: /limit продукты 2500 PLN month"
        category_text = self._extract_category_text(text, amount)
        category = self._normalize_category_name(category_text)
        if not category:
            return "Не понял категорию. Пример: установи лимит на продукты 2500 злотых в месяц"
        period = "Weekly" if self._mentions_week(text) else "Monthly"
        limit_id = f"LIM-{datetime.now(ZoneInfo(self._settings.timezone)).strftime('%Y%m%d%H%M%S')}"
        self._sheets.append_limit(
            limit_id=limit_id,
            scope="Category",
            category=category,
            subcategory="",
            period=period,
            amount_pln=amount,
            alert_thresholds=[80, 100],
            recipients="Both",
            created_by=person.value,
            description=text,
        )
        period_text = "неделю" if period == "Weekly" else "месяц"
        return f"Лимит установлен: {category} {amount:,.2f} PLN за {period_text}. Оповещу вас обоих на 80% и 100%."

    def create_balance_alert(self, text: str, person: Person) -> str:
        amount = self._extract_amount(text)
        if amount is None:
            return "Не понял сумму алерта. Пример: /alert balance below 10000 PLN"
        limit_id = f"BAL-{datetime.now(ZoneInfo(self._settings.timezone)).strftime('%Y%m%d%H%M%S')}"
        self._sheets.append_limit(
            limit_id=limit_id,
            scope="Balance",
            category="",
            subcategory="",
            period="Current",
            amount_pln=amount,
            alert_thresholds=[100],
            recipients="Both",
            created_by=person.value,
            description=text,
        )
        return f"Балансовый алерт установлен: сообщу вам обоим, если семейный баланс опустится до {amount:,.2f} PLN или ниже."

    def limits_summary(self) -> str:
        active_limits = [limit for limit in self._sheets.read_limits() if limit.active]
        if not active_limits:
            return "Активных лимитов пока нет."
        transactions = self._sheets.read_transactions()
        dashboard = self._sheets.read_dashboard()
        lines = ["Активные лимиты:"]
        for limit in active_limits:
            if limit.scope == "Balance":
                balance = self._parse_dashboard_amount(dashboard.get("Net Savings"))
                current = f"{balance:,.2f}" if balance is not None else "n/a"
                lines.append(f"- Balance ниже {limit.amount_pln:,.2f} PLN. Сейчас: {current} PLN")
                continue
            start, end, _ = self._period_bounds(limit.period.lower(), previous=False)
            spent = self._spent_for_limit(limit, transactions, start, end)
            lines.append(f"- {limit.category}: {spent:,.2f} / {limit.amount_pln:,.2f} PLN ({limit.period})")
        return "\n".join(lines)

    def delete_limit(self, category_text: str) -> str:
        category = self._normalize_category_name(category_text)
        if not category:
            return "Не понял, какой лимит удалить. Пример: /delete_limit продукты"
        for limit in self._sheets.read_limits():
            if limit.active and limit.scope == "Category" and limit.category == category:
                self._sheets.deactivate_limit(limit.row_number)
                return f"Лимит {category} отключен."
        return f"Активный лимит для {category} не найден."

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

    def recipient_chat_ids(self) -> list[int]:
        return [self._settings.konstantin_telegram_id, self._settings.svitlana_telegram_id]

    def _category_limit_alert(self, limit: BudgetLimit, transactions: list[SheetTransaction]) -> str | None:
        start, end, title = self._period_bounds(limit.period.lower(), previous=False)
        spent = self._spent_for_limit(limit, transactions, start, end)
        percent = spent / limit.amount_pln * 100 if limit.amount_pln else 0
        crossed = [threshold for threshold in sorted(limit.alert_thresholds) if percent >= threshold]
        if not crossed:
            return None
        threshold = crossed[-1]
        alert_key = f"{limit.limit_id}:{start.isoformat()}:{threshold}"
        if limit.last_alert_key == alert_key:
            return None
        self._sheets.update_limit_alert_key(limit.row_number, alert_key)
        if threshold >= 100:
            headline = "Лимит достигнут"
            extra = f"Перелимит: {max(spent - limit.amount_pln, 0):,.2f} PLN"
        else:
            headline = "Лимит почти достигнут"
            extra = f"Осталось: {max(limit.amount_pln - spent, 0):,.2f} PLN"
        return "\n".join(
            [
                f"{headline}: {limit.category}",
                f"{spent:,.2f} / {limit.amount_pln:,.2f} PLN ({percent:.0f}%)",
                f"Период: {title}",
                extra,
            ]
        )

    def _balance_alert(self, limit: BudgetLimit, dashboard: dict[str, str]) -> str | None:
        balance = self._parse_dashboard_amount(dashboard.get("Net Savings"))
        if balance is None or balance > limit.amount_pln:
            return None
        alert_key = f"{limit.limit_id}:below:{limit.amount_pln:g}"
        if limit.last_alert_key == alert_key:
            return None
        self._sheets.update_limit_alert_key(limit.row_number, alert_key)
        return "\n".join(
            [
                "Балансовый алерт:",
                f"Семейный баланс {balance:,.2f} PLN.",
                f"Порог: {limit.amount_pln:,.2f} PLN.",
            ]
        )

    def _limit_report_lines(self, period: str, start: date, end: date) -> list[str]:
        transactions = self._sheets.read_transactions()
        lines = []
        period_name = "Weekly" if period == "week" else "Monthly"
        for limit in self._sheets.read_limits():
            if not limit.active or limit.scope != "Category" or limit.period != period_name:
                continue
            spent = self._spent_for_limit(limit, transactions, start, end)
            percent = spent / limit.amount_pln * 100 if limit.amount_pln else 0
            lines.append(f"- {limit.category}: {spent:,.2f} / {limit.amount_pln:,.2f} PLN ({percent:.0f}%)")
        return lines

    def _spent_for_limit(
        self,
        limit: BudgetLimit,
        transactions: list[SheetTransaction],
        start: date,
        end: date,
    ) -> float:
        return sum(
            tx.amount
            for tx in transactions
            if tx.tx_type == "Expense"
            and start <= tx.date <= end
            and tx.category == limit.category
            and (not limit.subcategory or tx.subcategory == limit.subcategory)
        )

    def _period_bounds(self, period: str, *, previous: bool) -> tuple[date, date, str]:
        today = datetime.now(ZoneInfo(self._settings.timezone)).date()
        if period in {"week", "weekly"}:
            start = today - timedelta(days=today.weekday())
            if previous:
                start -= timedelta(days=7)
            end = start + timedelta(days=6)
            title = f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
            return start, end, title
        start = today.replace(day=1)
        if previous:
            start = (start - timedelta(days=1)).replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        end = next_month - timedelta(days=1)
        title = start.strftime("%m.%Y")
        return start, end, title

    def _extract_amount(self, text: str) -> float | None:
        match = re.search(r"(\d+(?:[\s.,]\d{3})*(?:[,.]\d+)?)", text)
        if not match:
            return None
        try:
            return self._parse_number(match.group(1))
        except ValueError:
            return None

    def _extract_category_text(self, text: str, amount: float) -> str:
        before_amount = text[: text.find(str(int(amount))) if float(amount).is_integer() and str(int(amount)) in text else len(text)]
        lower = before_amount.lower()
        for marker in ("лимит на", "ліміт на", "/limit"):
            if marker in lower:
                lower = lower.split(marker, 1)[1]
                break
        return lower.strip(" :,-")

    def _normalize_category_name(self, value: str) -> str | None:
        normalized = value.strip().lower()
        normalized = re.sub(r"\b(на|for|по|категорию|категорію|category|лимит|ліміт|удали|удалить)\b", " ", normalized)
        words = [word for word in re.split(r"[\s,;:/-]+", normalized) if word]
        candidates = [normalized, *words]
        for candidate in candidates:
            if candidate in CATEGORY_ALIASES:
                return CATEGORY_ALIASES[candidate]
        for category in set(CATEGORY_ALIASES.values()):
            if category.lower() in normalized:
                return category
        return None

    def _mentions_week(self, text: str) -> bool:
        lower = text.lower()
        return any(marker in lower for marker in ("week", "недел", "тиж"))

    def _is_limit_create_request(self, lower: str) -> bool:
        if lower.startswith("/limit"):
            return True
        return any(
            phrase in lower
            for phrase in (
                "установи лимит",
                "поставь лимит",
                "создай лимит",
                "добавь лимит",
                "зроби ліміт",
                "встанови ліміт",
                "постав ліміт",
                "set limit",
                "make limit",
                "make лимит",
            )
        )

    def _parse_dashboard_amount(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            return self._parse_number(value)
        except ValueError:
            return None

    def _parse_number(self, value: object) -> float:
        text = str(value).replace("\u00a0", "").replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            whole, fraction = text.rsplit(",", 1)
            text = whole + fraction if len(fraction) == 3 else f"{whole}.{fraction}"
        return float(text)
