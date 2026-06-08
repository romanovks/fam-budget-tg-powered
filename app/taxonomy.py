from app.models import TransactionType


ALLOWED_ACCOUNTS = {
    "Family Card",
    "Konstantin Card",
    "Svitlana Card",
    "Cash PLN",
    "Revolut",
    "Crypto USD",
    "SWIFT",
}

CATEGORY_PAIRS: dict[TransactionType, set[tuple[str, str]]] = {
    TransactionType.EXPENSE: {
        ("Groceries", "Supermarket"),
        ("Groceries", "Convenience store"),
        ("Groceries", "Market"),
        ("Groceries", "Household food"),
        ("Groceries", "Household supplies"),
        ("Restaurants", "Restaurant"),
        ("Restaurants", "Cafe"),
        ("Restaurants", "Delivery"),
        ("Restaurants", "Coffee"),
        ("Restaurants", "Fast food"),
        ("Transport", "Taxi"),
        ("Transport", "Public transport"),
        ("Transport", "Fuel"),
        ("Transport", "Parking"),
        ("Transport", "Car maintenance"),
        ("Housing", "Rent"),
        ("Housing", "Mortgage"),
        ("Housing", "Utilities"),
        ("Housing", "Electricity"),
        ("Housing", "Water"),
        ("Housing", "Gas"),
        ("Housing", "Internet"),
        ("Housing", "Mobile"),
        ("Housing", "Cleaning"),
        ("Housing", "Parking"),
        ("Housing", "Repairs"),
        ("Child", "Clothes"),
        ("Child", "Toys"),
        ("Child", "Education"),
        ("Child", "Activities"),
        ("Child", "Health"),
        ("Health", "Doctor"),
        ("Health", "Medicine"),
        ("Health", "Dental"),
        ("Health", "Insurance"),
        ("Health", "Laboratory"),
        ("Sport", "Gym"),
        ("Sport", "Gym membership"),
        ("Sport", "Sports diagnostics"),
        ("Sport", "Swimming"),
        ("Sport", "Bike"),
        ("Sport", "Running"),
        ("Sport", "Events"),
        ("Sport", "Equipment"),
        ("Tobacco", "IQOS sticks"),
        ("Tobacco", "Cigarettes"),
        ("Tobacco", "Vape"),
        ("Travel", "Flights"),
        ("Travel", "Hotels"),
        ("Travel", "Car rental"),
        ("Travel", "Food during travel"),
        ("Travel", "Activities"),
        ("Shopping", "Clothes"),
        ("Shopping", "Electronics"),
        ("Shopping", "Home goods"),
        ("Shopping", "Cosmetics"),
        ("Subscriptions", "Software"),
        ("Subscriptions", "Streaming"),
        ("Subscriptions", "Apps"),
        ("Subscriptions", "Cloud services"),
        ("Entertainment", "Cinema"),
        ("Entertainment", "Events"),
        ("Entertainment", "Games"),
        ("Entertainment", "Books"),
        ("Gifts", "Family gifts"),
        ("Gifts", "Friends gifts"),
        ("Gifts", "Donations"),
        ("Professional Services", "Accounting"),
        ("Professional Services", "Legal"),
        ("Professional Services", "Consulting"),
        ("Fees & Banking", "Bank fees"),
        ("Fees & Banking", "Exchange fees"),
        ("Fees & Banking", "Taxes"),
        ("Debt & Credit", "Credit limit repayment"),
        ("Debt & Credit", "Loan payment"),
        ("Debt & Credit", "Interest"),
        ("Other", "Uncategorized"),
    },
    TransactionType.INCOME: {
        ("Salary", "Main salary"),
        ("Salary", "Bonus"),
        ("Business", "Profit share"),
        ("Business", "Dividends"),
        ("Freelance", "Consulting"),
        ("Freelance", "Side income"),
        ("Refund", "Returned purchase"),
        ("Refund", "Reimbursement"),
        ("Other Income", "Other"),
    },
    TransactionType.TRANSFER: {("Other", "Uncategorized")},
    TransactionType.REFUND: {("Refund", "Returned purchase"), ("Refund", "Reimbursement")},
    TransactionType.ADJUSTMENT: {("Other", "Uncategorized")},
}


DEFAULT_SUBCATEGORY_BY_CATEGORY = {
    "Groceries": "Supermarket",
    "Restaurants": "Restaurant",
    "Transport": "Public transport",
    "Housing": "Utilities",
    "Child": "Activities",
    "Health": "Doctor",
    "Sport": "Gym",
    "Tobacco": "IQOS sticks",
    "Travel": "Activities",
    "Shopping": "Home goods",
    "Subscriptions": "Apps",
    "Entertainment": "Events",
    "Gifts": "Family gifts",
    "Professional Services": "Accounting",
    "Fees & Banking": "Bank fees",
    "Debt & Credit": "Credit limit repayment",
    "Other": "Uncategorized",
}


CATEGORY_KEYWORDS: list[tuple[tuple[str, ...], tuple[str, str]]] = [
    (("iqos", "heets", "стики", "стіки", "сигарет", "cigarette"), ("Tobacco", "IQOS sticks")),
    (("vape", "вейп"), ("Tobacco", "Vape")),
    (("электроэнерг", "електроенерг", "electricity", "prad", "prąd", "свет"), ("Housing", "Electricity")),
    (("газ", "gas"), ("Housing", "Gas")),
    (("water", "вода", "woda"), ("Housing", "Water")),
    (("коммун", "комун", "czynsz", "rent", "аренда", "оренда", "квартира"), ("Housing", "Rent")),
    (("internet", "интернет", "інтернет"), ("Housing", "Internet")),
    (("mobile", "мобиль", "мобіль", "телефон"), ("Housing", "Mobile")),
    (("parking", "парковка", "паркинг", "паркінг"), ("Transport", "Parking")),
    (("carrefour", "карефур", "biedronka", "lidl", "auchan", "ашан"), ("Groceries", "Supermarket")),
    (("zabka", "żabka", "жабка"), ("Groceries", "Convenience store")),
    (("продукт", "продукт", "grocer", "supermarket", "супермаркет", "market"), ("Groceries", "Supermarket")),
    (("mcdonald", "макдональдс", "kfc", "burger king"), ("Restaurants", "Fast food")),
    (("restaurant", "ресторан", "кафе", "cafe", "coffee", "кофе", "кава"), ("Restaurants", "Restaurant")),
    (("delivery", "glovo", "uber eats", "bolt food", "wolt", "доставка"), ("Restaurants", "Delivery")),
    (("taxi", "uber", "bolt", "такси"), ("Transport", "Taxi")),
    (("fuel", "бензин", "paliwo", "топливо", "пальне"), ("Transport", "Fuel")),
    (("multisport", "gym", "спортзал", "зал", "абонемент"), ("Sport", "Gym membership")),
    (("газоанализ", "газоаналіз", "лаборатор", "sport test", "sports test"), ("Sport", "Sports diagnostics")),
    (("doctor", "врач", "лікар", "лекар", "medicine", "аптека", "pharmacy"), ("Health", "Doctor")),
    (("dent", "стоматолог"), ("Health", "Dental")),
    (("бухгалтер", "accountant", "accounting", "księgow", "ksiegow"), ("Professional Services", "Accounting")),
    (("налог", "подат", "tax"), ("Fees & Banking", "Taxes")),
    (("bank fee", "комис", "коміс", "exchange fee"), ("Fees & Banking", "Bank fees")),
    (("кредит", "credit", "loan", "лимит", "ліміт"), ("Debt & Credit", "Credit limit repayment")),
]


def taxonomy_prompt() -> str:
    lines = []
    for tx_type, pairs in CATEGORY_PAIRS.items():
        allowed = ", ".join(f"{category}/{subcategory}" for category, subcategory in sorted(pairs))
        lines.append(f"{tx_type.value}: {allowed}")
    return "\n".join(lines)


def normalize_category(
    tx_type: TransactionType,
    category: str,
    subcategory: str,
    *,
    merchant: str = "",
    description: str = "",
) -> tuple[str, str, bool]:
    pair = (category, subcategory)
    context_pair = _infer_expense_category(" ".join([category, subcategory, merchant, description]))
    if tx_type == TransactionType.EXPENSE and pair == ("Other", "Uncategorized") and context_pair:
        return context_pair[0], context_pair[1], True
    if pair in CATEGORY_PAIRS.get(tx_type, set()):
        return category, subcategory, False
    lower_pair = (category.strip().lower(), subcategory.strip().lower())
    for allowed_category, allowed_subcategory in CATEGORY_PAIRS.get(tx_type, set()):
        if lower_pair == (allowed_category.lower(), allowed_subcategory.lower()):
            return allowed_category, allowed_subcategory, True
    if tx_type == TransactionType.EXPENSE and context_pair:
        return context_pair[0], context_pair[1], True
    if tx_type == TransactionType.EXPENSE:
        normalized_category = _known_expense_category(category)
        if normalized_category:
            return normalized_category, DEFAULT_SUBCATEGORY_BY_CATEGORY[normalized_category], True
    if tx_type == TransactionType.INCOME:
        return "Other Income", "Other", True
    if tx_type == TransactionType.REFUND:
        return "Refund", "Reimbursement", True
    return "Other", "Uncategorized", True


def _known_expense_category(category: str) -> str | None:
    normalized = category.strip().lower()
    for allowed_category, _ in CATEGORY_PAIRS[TransactionType.EXPENSE]:
        if normalized == allowed_category.lower():
            return allowed_category
    return None


def _infer_expense_category(text: str) -> tuple[str, str] | None:
    normalized = text.lower().replace("ё", "е")
    for keywords, pair in CATEGORY_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return pair
    return None


def normalize_account(account: str, fallback: str) -> tuple[str, bool]:
    if account in ALLOWED_ACCOUNTS:
        return account, False
    return fallback, True
