import datetime
import re

import pytest

from gnucash_quick_expense import accounts
from gnucash_quick_expense import ledger
from gnucash_quick_expense import money

JPY_CASH = accounts.Account("g-jpy-cash", "Assets:Yen:Cash", "c-jpy", "JPY", 1, True)
USD_CASH = accounts.Account(
    "g-usd-cash", "Assets:Dollar:Cash", "c-usd", "USD", 100, True
)
DINING = accounts.Account("g-dining", "Expenses:Food:Dining", "c-jpy", "JPY", 1, True)
NOW = datetime.datetime(2026, 10, 31, 3, 4, 5, tzinfo=datetime.UTC)
GUID = re.compile(r"[0-9a-f]{32}")


def _expense(**overrides) -> ledger.Expense:
    values = {
        "post_date": datetime.date(2026, 10, 30),
        "description": "",
        "from_account": JPY_CASH,
        "to_account": DINING,
        "amount": money.Rational(1200, 1),
        "to_quantity": money.Rational(1200, 1),
    }
    values.update(overrides)
    return ledger.Expense(**values)


def test_build_same_currency():
    tx, splits = ledger.build(_expense(), NOW)
    assert tx["currency_guid"] == "c-jpy"
    assert tx["post_date"] == datetime.datetime(
        2026, 10, 30, 10, 59, tzinfo=datetime.UTC
    )
    assert tx["enter_date"] == NOW
    assert tx["num"] == ""
    assert tx["description"] == ""
    assert [s["account_guid"] for s in splits] == ["g-jpy-cash", "g-dining"]
    assert [(s["value_num"], s["quantity_num"]) for s in splits] == [
        (-1200, -1200),
        (1200, 1200),
    ]
    for split in splits:
        assert split["tx_guid"] == tx["guid"]
        assert split["value_denom"] == split["quantity_denom"] == 1
        assert split["reconcile_state"] == "n"
        assert split["reconcile_date"] is None
        assert split["lot_guid"] is None
        assert split["memo"] == split["action"] == ""
    guids = [str(tx["guid"]), *(str(s["guid"]) for s in splits)]
    assert all(GUID.fullmatch(g) for g in guids)
    assert len(set(guids)) == 3


def test_build_foreign_cash():
    tx, (source, target) = ledger.build(
        _expense(
            from_account=USD_CASH,
            amount=money.Rational(1250, 100),
            to_quantity=money.Rational(1969, 1),
        ),
        NOW,
    )
    assert tx["currency_guid"] == "c-usd"
    assert (source["value_num"], source["value_denom"]) == (-1250, 100)
    assert (source["quantity_num"], source["quantity_denom"]) == (-1250, 100)
    assert (target["value_num"], target["value_denom"]) == (1250, 100)
    assert (target["quantity_num"], target["quantity_denom"]) == (1969, 1)


def test_build_keeps_the_description():
    tx, _ = ledger.build(_expense(description="Lunch"), NOW)
    assert tx["description"] == "Lunch"


def test_build_rejects_a_naive_now():
    with pytest.raises(ValueError):
        ledger.build(_expense(), NOW.replace(tzinfo=None))


def test_clean_description():
    assert ledger.clean_description("  Lunch\nwith\tA ") == "Lunch with A"
    assert ledger.clean_description("a\r\n\r\nb") == "a b"
    assert ledger.clean_description("") == ""
    assert ledger.clean_description("x" * 2048) == "x" * 2048
    with pytest.raises(ledger.EntryError):
        ledger.clean_description("x" * 2049)


def test_clean_description_keeps_other_spacing():
    assert ledger.clean_description("Lunch  with\u3000A") == "Lunch  with\u3000A"
