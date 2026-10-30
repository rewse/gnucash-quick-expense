import decimal

import pytest

from gnucash_quick_expense import money


@pytest.mark.parametrize(
    ("text", "fraction", "expected"),
    [
        ("1200", 1, money.Rational(1200, 1)),
        (" 1200 ", 1, money.Rational(1200, 1)),
        ("12.5", 100, money.Rational(1250, 100)),
        ("12.50", 100, money.Rational(1250, 100)),
        ("0.01", 100, money.Rational(1, 100)),
        ("3965", 100, money.Rational(396500, 100)),
    ],
)
def test_parse_amount_accepts(text, fraction, expected):
    assert money.parse_amount(text, fraction) == expected


@pytest.mark.parametrize(
    ("text", "fraction"),
    [
        ("", 1),
        ("0", 1),
        ("0.00", 100),
        ("-5", 1),
        ("+5", 1),
        ("1e3", 1),
        (".5", 100),
        ("5.", 100),
        ("1.5", 1),
        ("1.234", 100),
        ("1,200", 1),
        ("１２００", 1),
        ("NaN", 1),
        ("Infinity", 1),
        ("12 34", 1),
    ],
)
def test_parse_amount_rejects(text, fraction):
    with pytest.raises(money.AmountError):
        money.parse_amount(text, fraction)


@pytest.mark.parametrize("fraction", [0, 3, 50, -10])
def test_parse_amount_rejects_fractions_that_are_not_powers_of_ten(fraction):
    with pytest.raises(ValueError) as raised:
        money.parse_amount("1", fraction)
    assert not isinstance(raised.value, money.AmountError)


def test_parse_amount_keeps_every_digit_up_to_the_bigint_limit():
    # value_num is a PostgreSQL bigint.
    assert money.parse_amount("92233720368547758.07", 100) == money.Rational(
        2**63 - 1, 100
    )


@pytest.mark.parametrize(
    ("text", "fraction"),
    [("92233720368547758.08", 100), ("1" * 29, 1), ("9" * 30 + ".99", 100)],
)
def test_parse_amount_rejects_amounts_beyond_bigint(text, fraction):
    with pytest.raises(money.AmountError):
        money.parse_amount(text, fraction)


def test_convert_rejects_results_beyond_bigint():
    with pytest.raises(money.AmountError):
        money.convert(decimal.Decimal("1" * 30), decimal.Decimal(1), 100)


def test_convert_rounds_half_up_to_the_target_fraction():
    rate = decimal.Decimal("157.54")
    assert money.convert(decimal.Decimal("1.00"), rate, 1) == money.Rational(158, 1)
    # 3965.00 TWD at 4.87 JPY is 19309.55 JPY.
    assert money.convert(
        decimal.Decimal("3965.00"), decimal.Decimal("4.87"), 1
    ) == money.Rational(19310, 1)
    assert money.convert(
        decimal.Decimal(10), decimal.Decimal("0.125"), 100
    ) == money.Rational(125, 100)


def test_to_decimal():
    assert money.to_decimal(money.Rational(1250, 100)) == decimal.Decimal("12.50")
    assert money.to_decimal(money.Rational(1200, 1)) == decimal.Decimal(1200)


def test_format_amount():
    assert money.format_amount(money.Rational(123450, 100)) == "1234.50"
    assert money.format_amount(money.Rational(1200, 1)) == "1200"
    assert money.format_amount(money.Rational(-5, 100)) == "-0.05"
