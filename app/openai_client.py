import base64
import json
from pathlib import Path

from openai import OpenAI

from app.config import Settings
from app.models import ParseResult, Person
from app.taxonomy import taxonomy_prompt


SYSTEM_PROMPT = """
You parse family-budget messages into strict JSON for Google Sheets.

Spreadsheet rules:
- Person must be either Konstantin or Svitlana.
- Amounts are always positive.
- Direction is represented by type: Expense, Income, Transfer, Refund, Adjustment.
- If a message contains multiple unrelated expenses, split them into separate transactions.
- Keep the original currency from the user. Currency conversion happens in code later.
- Prefer existing categories/subcategories from the supplied taxonomy.
- If category/account/date is unclear, still return a transaction with Medium or Low confidence and Needs Review.
- The Telegram sender is authoritative: person and payment_owner must match telegram_person.
- Use Family for shared household expenses. Use Konstantin Personal or Svitlana Personal for clearly personal expenses.
- For sport/gym/MultiSport/lab sport tests for Konstantin, use Konstantin Personal.
- Default dates should use the provided current_date.
- Return JSON only, with exactly this top-level shape:
  {"raw_language":"ru|uk|pl|en|unknown","summary":"short summary","transactions":[...]}
- Every transaction must include: date, person, type, category, subcategory, amount, currency, account,
  payment_owner, family_personal, merchant, description, confidence, review_status, notes.
- Currency must be one of these ISO codes only: PLN, USD, EUR, GBP, UAH. Never return "zloty",
  "злотый", "гривна", "$", "zl", or "zł".
- review_status must be either OK or Needs Review.
- Use OK for normal parsed transactions. Use Needs Review only when amount, currency, date, or intent is genuinely ambiguous.
- confidence must be High, Medium, or Low.
""".strip()


class BudgetOpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = OpenAI(api_key=settings.openai_api_key)

    def parse_text(
        self,
        *,
        text: str,
        person: Person,
        current_date: str,
        default_account: str,
    ) -> ParseResult:
        completion = self._client.chat.completions.create(
            model=self._settings.openai_parse_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "current_date": current_date,
                            "telegram_person": person.value,
                            "default_account": default_account,
                            "taxonomy": taxonomy_prompt(),
                            "message": text,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("OpenAI parser returned no structured result")
        return self._parse_result(
            content=content,
            current_date=current_date,
            person=person,
            default_account=default_account,
            original_text=text,
        )

    def parse_image(
        self,
        *,
        image_path: Path,
        mime_type: str,
        caption: str,
        person: Person,
        current_date: str,
        default_account: str,
    ) -> ParseResult:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        completion = self._client.chat.completions.create(
            model=self._settings.openai_vision_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "current_date": current_date,
                                    "telegram_person": person.value,
                                    "default_account": default_account,
                                    "taxonomy": taxonomy_prompt(),
                                    "caption": caption,
                                    "task": "Read the receipt/photo and extract budget transactions.",
                                },
                                ensure_ascii=False,
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_type};base64,{encoded}",
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("OpenAI parser returned no structured result")
        return self._parse_result(
            content=content,
            current_date=current_date,
            person=person,
            default_account=default_account,
            original_text=caption or "photo receipt",
        )

    def transcribe_audio(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio_file:
            transcription = self._client.audio.transcriptions.create(
                model=self._settings.openai_transcribe_model,
                file=audio_file,
                response_format="text",
            )
        return str(transcription)

    def _parse_result(
        self,
        *,
        content: str,
        current_date: str,
        person: Person,
        default_account: str,
        original_text: str,
    ) -> ParseResult:
        payload = json.loads(content)
        payload.setdefault("raw_language", "unknown")
        payload.setdefault("summary", original_text[:160] or "Parsed Telegram message")
        payload["transactions"] = [
            self._coerce_transaction(
                tx,
                current_date=current_date,
                person=person,
                default_account=default_account,
                original_text=original_text,
            )
            for tx in payload.get("transactions", [])
        ]
        return ParseResult.model_validate(payload)

    def _coerce_transaction(
        self,
        tx: dict,
        *,
        current_date: str,
        person: Person,
        default_account: str,
        original_text: str,
    ) -> dict:
        tx = dict(tx)
        tx["date"] = tx.get("date") or current_date
        tx["person"] = person.value
        tx["type"] = self._coerce_type(tx.get("type"))
        tx["category"] = tx.get("category") or "Other"
        tx["subcategory"] = tx.get("subcategory") or "Uncategorized"
        tx["currency"] = self._coerce_currency(tx.get("currency"))
        tx["account"] = tx.get("account") or default_account
        tx["payment_owner"] = self._coerce_payment_owner(tx.get("payment_owner"), person)
        tx["family_personal"] = self._coerce_family_personal(tx.get("family_personal"), person)
        tx["merchant"] = self._coerce_merchant(tx.get("merchant") or tx.get("vendor"), original_text)
        tx["description"] = tx.get("description") or original_text[:200] or tx["merchant"]
        tx["confidence"] = self._coerce_confidence(tx.get("confidence"), tx.get("flags"))
        tx["review_status"] = self._coerce_review_status(tx.get("review_status"), tx.get("flags"))
        tx["notes"] = tx.get("notes") or ""
        return tx

    def _coerce_payment_owner(self, value, person: Person) -> str:
        return person.value

    def _coerce_family_personal(self, value, person: Person) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"family", "shared", "household", "семья", "сім'я", "семейное", "спільне", "общее"}:
            return "Family"
        if normalized in {"konstantin personal", "konstantin", "костя", "константин"}:
            return "Konstantin Personal"
        if normalized in {"svitlana personal", "svitlana", "светлана", "света"}:
            return "Svitlana Personal"
        if normalized in {"personal", "личное", "особисте"}:
            return f"{person.value} Personal"
        return "Family"

    def _coerce_merchant(self, value, original_text: str) -> str:
        merchant = str(value or "").strip()
        if merchant and merchant.lower() not in {"unknown", "n/a", "none", "неизвестно"}:
            return merchant
        normalized = original_text.lower()
        known_merchants = {
            "żabka": "Żabka",
            "zabka": "Żabka",
            "жабка": "Żabka",
            "carrefour": "Carrefour",
            "карефур": "Carrefour",
            "mcdonald": "McDonald's",
            "макдональдс": "McDonald's",
            "multisport": "MultiSport",
            "iqos": "IQOS",
            "бухгалтер": "Accountant",
            "электроэнерг": "Electricity",
            "електроенерг": "Electricity",
        }
        for marker, name in known_merchants.items():
            if marker in normalized:
                return name
        return "Unknown"

    def _coerce_currency(self, value) -> str:
        normalized = str(value or "PLN").strip().lower()
        mapping = {
            "pln": "PLN",
            "zl": "PLN",
            "zł": "PLN",
            "zloty": "PLN",
            "zlotych": "PLN",
            "злотый": "PLN",
            "злотых": "PLN",
            "злоті": "PLN",
            "злотих": "PLN",
            "usd": "USD",
            "$": "USD",
            "dollar": "USD",
            "dollars": "USD",
            "доллар": "USD",
            "долларов": "USD",
            "eur": "EUR",
            "€": "EUR",
            "euro": "EUR",
            "евро": "EUR",
            "gbp": "GBP",
            "£": "GBP",
            "uah": "UAH",
            "грн": "UAH",
            "гривна": "UAH",
            "гривен": "UAH",
            "гривень": "UAH",
        }
        return mapping.get(normalized, "PLN")

    def _coerce_type(self, value) -> str:
        normalized = str(value or "Expense").strip().lower()
        mapping = {
            "expense": "Expense",
            "расход": "Expense",
            "витрата": "Expense",
            "income": "Income",
            "доход": "Income",
            "надходження": "Income",
            "transfer": "Transfer",
            "refund": "Refund",
            "adjustment": "Adjustment",
        }
        return mapping.get(normalized, "Expense")

    def _coerce_confidence(self, value, flags) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"high", "medium", "low"}:
            return normalized.title()
        if flags:
            return "Medium"
        return "High"

    def _coerce_review_status(self, value, flags) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"ok", "corrected", "ignored"}:
            return "OK" if normalized == "ok" else "Needs Review"
        if normalized == "needs review":
            return "Needs Review"
        return "OK"
