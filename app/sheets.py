import base64
import json
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo

import google.auth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.models import NormalizedTransaction, ParseResult, Person


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LIMITS_SHEET = "Limits"
WEEKLY_REPORTS_SHEET = "Weekly Reports"
MONTHLY_REPORTS_SHEET = "Monthly Reports"
LIMITS_HEADERS = [
    "Limit ID",
    "Scope",
    "Category",
    "Subcategory",
    "Period",
    "Amount PLN",
    "Alert Thresholds",
    "Recipients",
    "Active",
    "Created By",
    "Created At",
    "Last Alert Key",
    "Description",
]
REPORT_HEADERS = [
    "Generated At",
    "Period",
    "Start Date",
    "End Date",
    "Total Expenses PLN",
    "Total Income PLN",
    "Net PLN",
    "Current Balance PLN",
    "Top Categories",
    "Limits",
    "Digest",
]


@dataclass(frozen=True)
class SheetTransaction:
    tx_id: str
    date: date
    person: str
    tx_type: str
    category: str
    subcategory: str
    amount: float


@dataclass(frozen=True)
class BudgetLimit:
    row_number: int
    limit_id: str
    scope: str
    category: str
    subcategory: str
    period: str
    amount_pln: float
    alert_thresholds: list[int]
    recipients: str
    active: bool
    created_by: str
    created_at: str
    last_alert_key: str
    description: str


class SheetsClient:
    def __init__(self, service_account_json: str | None, spreadsheet_id: str, timezone: str) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._timezone = timezone
        credentials = self._credentials(service_account_json)
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def _credentials(self, service_account_json: str | None):
        if service_account_json:
            service_info = self._parse_service_account_json(service_account_json)
            return Credentials.from_service_account_info(service_info, scopes=SCOPES)
        credentials, _ = google.auth.default(scopes=SCOPES)
        return credentials

    def _parse_service_account_json(self, value: str) -> dict:
        stripped = value.strip()
        if stripped.startswith("{"):
            return json.loads(stripped)
        return json.loads(base64.b64decode(stripped).decode("utf-8"))

    def already_processed(self, update_id: int) -> bool:
        values = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range="Raw Input!G:H")
            .execute()
            .get("values", [])
        )
        needle = f"TG-{update_id}"
        return any(needle in " ".join(row) for row in values)

    def append_raw_input(
        self,
        *,
        update_id: int,
        person: Person,
        raw_text: str,
        parse_result: ParseResult,
        transaction_ids: list[str],
    ) -> None:
        now = datetime.now(ZoneInfo(self._timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")
        row = [
            now,
            person.value,
            "text",
            raw_text,
            "",
            "Parsed" if transaction_ids else "Needs Review",
            f"TG-{update_id}. {parse_result.summary}",
            ", ".join(transaction_ids),
        ]
        self._append_values("Raw Input!A:H", [row])

    def append_transactions(self, transactions: list[NormalizedTransaction], transaction_ids: list[str]) -> None:
        rows = []
        now = datetime.now(ZoneInfo(self._timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")
        for tx_id, tx in zip(transaction_ids, transactions, strict=True):
            rows.append(
                [
                    tx_id,
                    tx.date,
                    now,
                    tx.person.value,
                    tx.type.value,
                    tx.category,
                    tx.subcategory,
                    tx.amount,
                    "PLN",
                    tx.account,
                    tx.payment_owner,
                    tx.family_personal,
                    tx.merchant,
                    tx.description,
                    "Telegram Bot",
                    f"TG-{tx_id}",
                    tx.confidence.value,
                    tx.review_status.value,
                    tx.notes,
                ]
            )
        self._append_values("Transactions!A:S", rows)

    def read_dashboard(self) -> dict[str, str]:
        values = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range="Dashboard!A4:B6")
            .execute()
            .get("values", [])
        )
        return {row[0]: row[1] for row in values if len(row) >= 2}

    def read_transactions(self) -> list[SheetTransaction]:
        values = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range="Transactions!A:S")
            .execute()
            .get("values", [])
        )
        transactions = []
        for row in values:
            tx = self._parse_transaction_row(row)
            if tx:
                transactions.append(tx)
        return transactions

    def read_limits(self) -> list[BudgetLimit]:
        self.ensure_limits_sheet()
        values = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=f"{LIMITS_SHEET}!A:M")
            .execute()
            .get("values", [])
        )
        limits = []
        for index, row in enumerate(values[1:], start=2):
            limit = self._parse_limit_row(index, row)
            if limit:
                limits.append(limit)
        return limits

    def append_limit(
        self,
        *,
        limit_id: str,
        scope: str,
        category: str,
        subcategory: str,
        period: str,
        amount_pln: float,
        alert_thresholds: list[int],
        recipients: str,
        created_by: str,
        description: str,
    ) -> None:
        self.ensure_limits_sheet()
        now = datetime.now(ZoneInfo(self._timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")
        row = [
            limit_id,
            scope,
            category,
            subcategory,
            period,
            amount_pln,
            ",".join(str(threshold) for threshold in alert_thresholds),
            recipients,
            "TRUE",
            created_by,
            now,
            "",
            description,
        ]
        self._append_values(f"{LIMITS_SHEET}!A:M", [row])

    def deactivate_limit(self, row_number: int) -> None:
        self._update_values(f"{LIMITS_SHEET}!I{row_number}", [["FALSE"]])

    def update_limit_alert_key(self, row_number: int, alert_key: str) -> None:
        self._update_values(f"{LIMITS_SHEET}!L{row_number}", [[alert_key]])

    def upsert_period_report(
        self,
        *,
        period: str,
        start: date,
        end: date,
        title: str,
        total_expenses: float,
        total_income: float,
        current_balance: str,
        top_categories: list[tuple[str, float]],
        limit_lines: list[str],
        report_text: str,
    ) -> None:
        sheet_name = WEEKLY_REPORTS_SHEET if period == "Weekly" else MONTHLY_REPORTS_SHEET
        self._ensure_sheet(sheet_name, REPORT_HEADERS)
        generated_at = datetime.now(ZoneInfo(self._timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")
        row = [
            generated_at,
            title,
            start.isoformat(),
            end.isoformat(),
            round(total_expenses, 2),
            round(total_income, 2),
            round(total_income - total_expenses, 2),
            current_balance,
            "\n".join(f"{category}: {amount:,.2f} PLN" for category, amount in top_categories),
            "\n".join(limit_lines),
            report_text,
        ]
        values = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=f"{sheet_name}!A:K")
            .execute()
            .get("values", [])
        )
        target_row = None
        for index, existing in enumerate(values[1:], start=2):
            existing_start = existing[2] if len(existing) > 2 else ""
            existing_end = existing[3] if len(existing) > 3 else ""
            if existing_start == start.isoformat() and existing_end == end.isoformat():
                target_row = index
                break
        if target_row:
            self._update_values(f"{sheet_name}!A{target_row}:K{target_row}", [row])
        else:
            self._append_values(f"{sheet_name}!A:K", [row])

    def update_digest_dashboard(
        self,
        *,
        period: str,
        title: str,
        total_expenses: float,
        total_income: float,
        current_balance: str,
        top_categories: list[tuple[str, float]],
    ) -> None:
        generated_at = datetime.now(ZoneInfo(self._timezone)).strftime("%Y-%m-%d %H:%M:%S %Z")
        rows = [
            ["Last Digest", generated_at],
            ["Digest Period", period],
            ["Digest Range", title],
            ["Digest Expenses PLN", round(total_expenses, 2)],
            ["Digest Income PLN", round(total_income, 2)],
            ["Digest Net PLN", round(total_income - total_expenses, 2)],
            ["Current Balance PLN", current_balance],
            ["Top Category 1", _format_top_category(top_categories, 0)],
            ["Top Category 2", _format_top_category(top_categories, 1)],
            ["Top Category 3", _format_top_category(top_categories, 2)],
        ]
        self._update_values("Dashboard!D4:E13", rows)

    def ensure_limits_sheet(self) -> None:
        self._ensure_sheet(LIMITS_SHEET, LIMITS_HEADERS)

    def _ensure_sheet(self, sheet_name: str, headers: list[str]) -> None:
        spreadsheet = (
            self._service.spreadsheets()
            .get(spreadsheetId=self._spreadsheet_id, fields="sheets.properties.title")
            .execute()
        )
        titles = {sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])}
        if sheet_name not in titles:
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=self._spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
            ).execute()
            if headers:
                self._update_values(f"{sheet_name}!A1:{_column_name(len(headers))}1", [headers])
            return

        values = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=f"{sheet_name}!A1:{_column_name(len(headers))}1")
            .execute()
            .get("values", [])
        )
        if headers and not values:
            self._update_values(f"{sheet_name}!A1:{_column_name(len(headers))}1", [headers])

    def _parse_transaction_row(self, row: list[str]) -> SheetTransaction | None:
        if len(row) < 9 or row[0] == "Transaction ID":
            return None
        try:
            tx_date = date.fromisoformat(row[1])
            amount = self._parse_amount(row[7])
        except (ValueError, TypeError):
            return None
        return SheetTransaction(
            tx_id=row[0],
            date=tx_date,
            person=row[3] if len(row) > 3 else "",
            tx_type=row[4] if len(row) > 4 else "",
            category=row[5] if len(row) > 5 else "",
            subcategory=row[6] if len(row) > 6 else "",
            amount=amount,
        )

    def _parse_limit_row(self, row_number: int, row: list[str]) -> BudgetLimit | None:
        if len(row) < 9 or not row[0]:
            return None
        try:
            amount = self._parse_amount(row[5])
        except (ValueError, TypeError):
            return None
        thresholds = []
        for value in (row[6] if len(row) > 6 else "80,100").split(","):
            try:
                thresholds.append(int(value.strip()))
            except ValueError:
                continue
        return BudgetLimit(
            row_number=row_number,
            limit_id=row[0],
            scope=row[1] if len(row) > 1 else "Category",
            category=row[2] if len(row) > 2 else "",
            subcategory=row[3] if len(row) > 3 else "",
            period=row[4] if len(row) > 4 else "Monthly",
            amount_pln=amount,
            alert_thresholds=thresholds or [80, 100],
            recipients=row[7] if len(row) > 7 else "Both",
            active=(row[8] if len(row) > 8 else "").strip().upper() == "TRUE",
            created_by=row[9] if len(row) > 9 else "",
            created_at=row[10] if len(row) > 10 else "",
            last_alert_key=row[11] if len(row) > 11 else "",
            description=row[12] if len(row) > 12 else "",
        )

    def _parse_amount(self, value: object) -> float:
        text = str(value).replace("\u00a0", "").replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            whole, fraction = text.rsplit(",", 1)
            text = whole + fraction if len(fraction) == 3 else f"{whole}.{fraction}"
        return float(text)

    def _append_values(self, range_name: str, rows: list[list[object]]) -> None:
        self._service.spreadsheets().values().append(
            spreadsheetId=self._spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()

    def _update_values(self, range_name: str, rows: list[list[object]]) -> None:
        self._service.spreadsheets().values().update(
            spreadsheetId=self._spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _format_top_category(top_categories: list[tuple[str, float]], index: int) -> str:
    if index >= len(top_categories):
        return ""
    category, amount = top_categories[index]
    return f"{category}: {amount:,.2f} PLN"
