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


def test_electricity_is_housing_category() -> None:
    assert normalize_category(
        TransactionType.EXPENSE,
        "Other",
        "Uncategorized",
        merchant="Unknown",
        description="Оплата электроэнергии коммуналка 490 злотых",
    ) == (
        "Housing",
        "Electricity",
        True,
    )


def test_iqos_sticks_are_tobacco_even_from_zabka() -> None:
    assert normalize_category(
        TransactionType.EXPENSE,
        "Other",
        "Uncategorized",
        merchant="Żabka",
        description="Żabka стики iqos 78 PLN",
    ) == (
        "Tobacco",
        "IQOS sticks",
        True,
    )


def test_unknown_account_falls_back() -> None:
    assert normalize_account("Mystery", "Family Card") == ("Family Card", True)
