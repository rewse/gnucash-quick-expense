"""Amounts as GnuCash stores them: integer numerators over integer denominators.

Floats are never used, so an amount entered as text reaches the database
without rounding.
"""

import decimal
import re
from typing import NamedTuple

_AMOUNT = re.compile(r"[0-9]+(?:\.[0-9]+)?", re.ASCII)


class AmountError(ValueError):
    """An amount that cannot be recorded."""


class Rational(NamedTuple):
    """A value of num / denom, as in the GnuCash value and quantity columns."""

    num: int
    denom: int


def _places(fraction: int) -> int:
    """Returns the number of decimal places a power-of-ten fraction allows."""
    text = str(fraction)
    if fraction < 1 or text != "1" + "0" * (len(text) - 1):
        raise AmountError(f"fraction must be a power of ten: {fraction}")
    return len(text) - 1


def parse_amount(text: str, fraction: int) -> Rational:
    """Parses a positive decimal amount into a Rational over `fraction`.

    Args:
        text: ASCII digits with an optional decimal point and digits after it.
            Surrounding whitespace is ignored; signs, exponents, separators,
            and non-ASCII digits are rejected.
        fraction: The commodity's smallest unit as a power of ten, such as 1
            for JPY or 100 for USD.

    Raises:
        AmountError: The text is not a positive amount the fraction can hold.
    """
    places = _places(fraction)
    stripped = text.strip()
    if not _AMOUNT.fullmatch(stripped):
        raise AmountError("Enter the amount as digits, such as 1200 or 12.50.")
    _, _, decimals = stripped.partition(".")
    if len(decimals) > places:
        raise AmountError(f"The amount allows at most {places} decimal places.")
    num = int(decimal.Decimal(stripped).scaleb(places))
    if num <= 0:
        raise AmountError("The amount must be greater than zero.")
    return Rational(num, fraction)


def to_decimal(value: Rational) -> decimal.Decimal:
    """Returns the exact decimal value of a power-of-ten Rational."""
    return decimal.Decimal(value.num).scaleb(-_places(value.denom))


def convert(amount: decimal.Decimal, rate: decimal.Decimal, fraction: int) -> Rational:
    """Multiplies by a rate and rounds half up to the target fraction."""
    places = _places(fraction)
    product = (amount * rate).quantize(
        decimal.Decimal(1).scaleb(-places), rounding=decimal.ROUND_HALF_UP
    )
    return Rational(int(product.scaleb(places)), fraction)


def format_amount(value: Rational) -> str:
    """Formats a Rational with exactly as many decimals as its denominator."""
    return f"{to_decimal(value):f}"
