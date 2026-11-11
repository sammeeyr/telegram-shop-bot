"""Money helpers. All amounts inside the app are integer cents to avoid float errors."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CENT = Decimal("0.01")
_MAX_AMOUNT = Decimal("100000000")  # sanity cap: 100M per single value


def to_cents(value: Decimal | str | int | float) -> int:
    amount = Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
    return int(amount * 100)


def parse_money(text: str) -> int | None:
    """Parse user input like ``12``, ``12.5``, ``12,50`` or ``$1,000.00`` into cents.

    Returns ``None`` when the input is not a positive, sane amount.
    """
    cleaned = text.strip().replace(" ", "").lstrip("$€£")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")  # 1,000.50 -> thousands separator
    else:
        cleaned = cleaned.replace(",", ".")  # 12,50 -> decimal comma
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount <= 0 or amount > _MAX_AMOUNT:
        return None
    cents = to_cents(amount)
    return cents if cents > 0 else None


def parse_signed_money(text: str) -> int | None:
    """Parse ``+10`` / ``-5.50`` / ``10`` into signed cents."""
    raw = text.strip()
    sign = 1
    if raw[:1] in {"+", "-"}:
        sign = -1 if raw[0] == "-" else 1
        raw = raw[1:]
    cents = parse_money(raw)
    return None if cents is None else sign * cents


def cents_to_decimal_str(cents: int) -> str:
    """Plain ``12.50`` representation for payment APIs."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def format_money(cents: int, symbol: str = "$") -> str:
    """Human readable ``$1,234.50``."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{symbol}{cents // 100:,}.{cents % 100:02d}"
