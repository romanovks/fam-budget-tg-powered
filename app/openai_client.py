import base64
import json
from pathlib import Path

from openai import OpenAI

from app.config import Settings
from app.models import ParseResult, Person


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
- Use Family for shared household expenses. Use Konstantin Personal or Svitlana Personal for clearly personal expenses.
- For sport/gym/MultiSport/lab sport tests for Konstantin, use Konstantin Personal.
- Default dates should use the provided current_date.
- Return JSON only.
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
        return ParseResult.model_validate_json(content)

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
        return ParseResult.model_validate_json(content)

    def transcribe_audio(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio_file:
            transcription = self._client.audio.transcriptions.create(
                model=self._settings.openai_transcribe_model,
                file=audio_file,
                response_format="text",
            )
        return str(transcription)
