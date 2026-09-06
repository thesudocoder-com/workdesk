from decimal import Decimal, ROUND_HALF_UP


DEFAULT_CURRENCY = "CAD"
ZERO = Decimal("0.00")


def money(value: Decimal | int | str | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_cad(value: Decimal | int | str | None) -> str:
    try:
        from Application.Settings.Service import get_workspace
        workspace = get_workspace()
        currency = workspace.currency if workspace else DEFAULT_CURRENCY
    except Exception:
        currency = DEFAULT_CURRENCY
    return format_currency(value, currency)


def format_currency(value: Decimal | int | str | None, currency: str) -> str:
    currency = (currency or DEFAULT_CURRENCY).upper()
    symbols = {"USD": "$", "CAD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}
    return f"{symbols.get(currency, '')}{money(value):,.2f} {currency}"
