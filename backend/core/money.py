"""Money helpers. All amounts are Decimal, rounded half-up to 2 places. Never float."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def D(value: object) -> Decimal:
    """Convert to Decimal without going through float rounding errors."""
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        value = repr(value)
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid amount: {value!r}") from exc


def money(value: object) -> Decimal:
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def pct_of(amount: object, rate: object) -> Decimal:
    """amount x rate (rate as a fraction, e.g. 0.07), rounded to cents."""
    return money(D(amount) * D(rate))
