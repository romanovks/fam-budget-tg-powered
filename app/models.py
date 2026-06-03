from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Person(StrEnum):
    KONSTANTIN = "Konstantin"
    SVITLANA = "Svitlana"


class TransactionType(StrEnum):
    EXPENSE = "Expense"
    INCOME = "Income"
    TRANSFER = "Transfer"
    REFUND = "Refund"
    ADJUSTMENT = "Adjustment"


class Currency(StrEnum):
    PLN = "PLN"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    UAH = "UAH"


class Confidence(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ReviewStatus(StrEnum):
    OK = "OK"
    NEEDS_REVIEW = "Needs Review"


class ParsedTransaction(BaseModel):
    date: str = Field(description="Transaction date in YYYY-MM-DD format")
    person: Person
    type: TransactionType
    category: str
    subcategory: str
    amount: float = Field(gt=0)
    currency: Currency
    account: str
    payment_owner: Literal["Family", "Konstantin", "Svitlana"]
    family_personal: Literal["Family", "Konstantin Personal", "Svitlana Personal"]
    merchant: str
    description: str
    confidence: Confidence
    review_status: ReviewStatus
    notes: str = ""

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        parts = value.split("-")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError("date must be YYYY-MM-DD")
        return value


class ParseResult(BaseModel):
    raw_language: str
    summary: str
    transactions: list[ParsedTransaction]


class NormalizedTransaction(ParsedTransaction):
    original_amount: float
    original_currency: Currency
    exchange_rate: float | None = None
    exchange_rate_source: str | None = None
