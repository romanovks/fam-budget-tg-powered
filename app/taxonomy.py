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
        ("Groceries", "Market"),
        ("Groceries", "Household food"),
        ("Restaurants", "Restaurant"),
        ("Restaurants", "Cafe"),
        ("Restaurants", "Delivery"),
        ("Restaurants", "Coffee"),
        ("Transport", "Taxi"),
        ("Transport", "Public transport"),
        ("Transport", "Fuel"),
        ("Transport", "Parking"),
        ("Transport", "Car maintenance"),
        ("Housing", "Rent"),
        ("Housing", "Mortgage"),
        ("Housing", "Utilities"),
        ("Housing", "Internet"),
        ("Housing", "Mobile"),
        ("Housing", "Cleaning"),
        ("Child", "Clothes"),
        ("Child", "Toys"),
        ("Child", "Education"),
        ("Child", "Activities"),
        ("Child", "Health"),
        ("Health", "Doctor"),
        ("Health", "Medicine"),
        ("Health", "Dental"),
        ("Health", "Insurance"),
        ("Sport", "Gym"),
        ("Sport", "Swimming"),
        ("Sport", "Bike"),
        ("Sport", "Running"),
        ("Sport", "Events"),
        ("Sport", "Equipment"),
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
        ("Fees & Banking", "Bank fees"),
        ("Fees & Banking", "Exchange fees"),
        ("Fees & Banking", "Taxes"),
        ("Debt & Credit", "Credit limit repayment"),
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


def normalize_category(tx_type: TransactionType, category: str, subcategory: str) -> tuple[str, str, bool]:
    pair = (category, subcategory)
    if pair in CATEGORY_PAIRS.get(tx_type, set()):
        return category, subcategory, False
    if tx_type == TransactionType.INCOME:
        return "Other Income", "Other", True
    if tx_type == TransactionType.REFUND:
        return "Refund", "Reimbursement", True
    return "Other", "Uncategorized", True


def normalize_account(account: str, fallback: str) -> tuple[str, bool]:
    if account in ALLOWED_ACCOUNTS:
        return account, False
    return fallback, True
