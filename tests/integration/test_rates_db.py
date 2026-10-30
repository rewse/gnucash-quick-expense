import datetime
import decimal

from gnucash_quick_expense import rates

from . import conftest


def test_gnucash_price_reads_the_latest_price_on_or_before_the_day(gnucash_db):
    quote = rates.gnucash_price(
        gnucash_db, conftest.TWD, conftest.JPY, datetime.date(2026, 10, 31)
    )
    assert quote == rates.Quote(
        decimal.Decimal("4.87"), datetime.date(2026, 8, 6), "GnuCash price"
    )
    same_day = rates.gnucash_price(
        gnucash_db, conftest.TWD, conftest.JPY, datetime.date(2026, 8, 6)
    )
    assert same_day is not None


def test_gnucash_price_ignores_later_prices(gnucash_db):
    assert (
        rates.gnucash_price(
            gnucash_db, conftest.TWD, conftest.JPY, datetime.date(2026, 8, 5)
        )
        is None
    )


def test_gnucash_price_inverts_a_price_quoted_the_other_way(gnucash_db):
    quote = rates.gnucash_price(
        gnucash_db, conftest.USD, conftest.JPY, datetime.date(2026, 10, 31)
    )
    assert quote is not None
    assert quote.rate == decimal.Decimal(150)
    assert quote.date == datetime.date(2026, 7, 31)


def test_gnucash_price_prefers_the_newest_of_both_directions(gnucash_db):
    gnucash_db.execute(
        "INSERT INTO prices (guid, commodity_guid, currency_guid, date, value_num,"
        " value_denom) VALUES ('p00000000000000000000000usdjpy00', %s, %s,"
        " '2026-06-30 10:59:00', 14000, 100)",
        (conftest.USD, conftest.JPY),
    )
    quote = rates.gnucash_price(
        gnucash_db, conftest.USD, conftest.JPY, datetime.date(2026, 10, 31)
    )
    assert quote is not None
    assert quote.rate == decimal.Decimal(150)
    earlier = rates.gnucash_price(
        gnucash_db, conftest.USD, conftest.JPY, datetime.date(2026, 7, 1)
    )
    assert earlier is not None
    assert earlier.rate == decimal.Decimal(140)


def test_gnucash_price_returns_none_without_prices(gnucash_db):
    assert (
        rates.gnucash_price(
            gnucash_db, conftest.TWD, conftest.USD, datetime.date(2026, 10, 31)
        )
        is None
    )
