from app.models import TransactionType
from app.taxonomy import normalize_account, normalize_category


def test_known_category_is_preserved() -> None:
    assert normalize_category(TransactionType.EXPENSE, "Groceries", "Supermarket") == (
        "Groceries",
        "Supermarket",
        False,
    )


def test_unknown_expense_category_falls_back() -> None:
    assert normalize_category(TransactionType.EXPENSE, "Smoke", "Sticks") == (
        "Other",
        "Uncategorized",
        True,
    )


def test_unknown_account_falls_back() -> None:
    assert normalize_account("Mystery", "Family Card") == ("Family Card", True)
