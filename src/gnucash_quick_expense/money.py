"""Amounts as GnuCash stores them: integer numerators over integer denominators.

Floats are never used, so an amount entered as text reaches the database
without rounding.
"""

import decimal
import re
from typing import NamedTuple

_AMOUNT = re.compile(r"([0-9]+)(?:\.([0-9]+))?", re.ASCII)

# GnuCash keeps value_num and quantity_num in PostgreSQL bigint columns.
_BIGINT_MAX = 2**63 - 1

# Enough significant digits that no product of a bigint-sized amount and an
# exchange rate is rounded before the final quantize.
_PRECISION = 60


class AmountError(ValueError):
    """An amount that cannot be recorded."""


class Rational(NamedTuple):
    """A value of num / denom, as in the GnuCash value and quantity columns."""

    num: int
    denom: int


def _places(fraction: int) -> int:
    """Returns the number of decimal places a power-of-ten fraction allows.

    Raises:
        ValueError: The fraction is not a positive power of ten. This signals
            inconsistent commodity data rather than a bad entry, so it is not
            an AmountError.
    """
    text = str(fraction)
    if fraction < 1 or text != "1" + "0" * (len(text) - 1):
        raise ValueError(f"fraction must be a power of ten: {fraction}")
    return len(text) - 1


def _checked(num: int, fraction: int) -> Rational:
    if num > _BIGINT_MAX:
        raise AmountError("The amount is too large.")
    return Rational(num, fraction)


def parse_amount(text: str, fraction: int) -> Rational:
    """Parses a positive decimal amount into a Rational over `fraction`.

    Args:
        text: ASCII digits with an optional decimal point and digits after it.
            Surrounding whitespace is ignored; signs, exponents, separators,
            and non-ASCII digits are rejected.
        fraction: The commodity's smallest unit as a power of ten, such as 1
            for JPY or 100 for USD.

    Returns:
        The amount as num / fraction, with every entered digit kept.

    Raises:
        AmountError: The text is not a positive amount the fraction and a
            bigint numerator can hold.
        ValueError: The fraction is not a power of ten.
    """
    places = _places(fraction)
    match = _AMOUNT.fullmatch(text.strip())
    if not match:
        raise AmountError("Enter the amount as digits, such as 1200 or 12.50.")
    whole, decimals = match.group(1), match.group(2) or ""
    if len(decimals) > places:
        raise AmountError(f"The amount allows at most {places} decimal places.")
    num = int(whole) * fraction + int(decimals.ljust(places, "0") or "0")
    if num <= 0:
        raise AmountError("The amount must be greater than zero.")
    return _checked(num, fraction)


def to_decimal(value: Rational) -> decimal.Decimal:
    """Returns the exact decimal value of a power-of-ten Rational.

    Raises:
        ValueError: The denominator is not a power of ten.
    """
    return decimal.Decimal(value.num).scaleb(
        -_places(value.denom), decimal.Context(prec=_PRECISION)
    )


def convert(amount: decimal.Decimal, rate: decimal.Decimal, fraction: int) -> Rational:
    """Converts an amount at a rate into another commodity.

    Args:
        amount: The amount in the source commodity.
        rate: Units of the target commodity per unit of the source.
        fraction: The target commodity's smallest unit as a power of ten.

    Returns:
        amount * rate rounded half up, once, to the target fraction. A tiny
        amount can round to zero; callers that need a positive quantity check
        the result.

    Raises:
        AmountError: The result does not fit a bigint numerator.
        ValueError: The fraction is not a power of ten.
    """
    places = _places(fraction)
    with decimal.localcontext(decimal.Context(prec=_PRECISION)):
        product = (amount * rate).quantize(
            decimal.Decimal(1).scaleb(-places), rounding=decimal.ROUND_HALF_UP
        )
        num = int(product.scaleb(places))
    return _checked(num, fraction)


def format_amount(value: Rational) -> str:
    """Formats a Rational with exactly as many decimals as its denominator.

    Raises:
        ValueError: The denominator is not a power of ten.
    """
    return f"{to_decimal(value):f}"
