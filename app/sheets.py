import base64
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.models import NormalizedTransaction, ParseResult, Person


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsClient:
    def __init__(self, service_account_json: str, spreadsheet_id: str, timezone: str) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._timezone = timezone
        service_info = self._parse_service_account_json(service_account_json)
        credentials = Credentials.from_service_account_info(service_info, scopes=SCOPES)
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

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

    def _append_values(self, range_name: str, rows: list[list[object]]) -> None:
        self._service.spreadsheets().values().append(
            spreadsheetId=self._spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
