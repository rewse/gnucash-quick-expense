"""The two-split transaction that records one expense."""

import datetime
import re
import uuid
from typing import NamedTuple

import psycopg

from gnucash_quick_expense import accounts
from gnucash_quick_expense import money

# GnuCash's own time for a transaction entered by date alone.
_POST_TIME = datetime.time(10, 59, tzinfo=datetime.UTC)
_DESCRIPTION_MAX = 2048
# Line breaks and tabs; other spacing, such as an ideographic space, stays.
_BREAKS = re.compile(r"[\t\n\v\f\r]+")

_TRANSACTION_SQL = """
INSERT INTO transactions (guid, currency_guid, num, post_date, enter_date, description)
VALUES (%(guid)s, %(currency_guid)s, %(num)s, %(post_date)s, %(enter_date)s,
        %(description)s)
"""

_SPLIT_SQL = """
INSERT INTO splits (guid, tx_guid, account_guid, memo, action, reconcile_state,
                    reconcile_date, value_num, value_denom, quantity_num,
                    quantity_denom, lot_guid)
VALUES (%(guid)s, %(tx_guid)s, %(account_guid)s, %(memo)s, %(action)s,
        %(reconcile_state)s, %(reconcile_date)s, %(value_num)s, %(value_denom)s,
        %(quantity_num)s, %(quantity_denom)s, %(lot_guid)s)
"""


class EntryError(ValueError):
    """An expense that cannot be recorded as entered."""


class Expense(NamedTuple):
    """One expense paid from an asset account into an expense account.

    Attributes:
        post_date: The day of the expense.
        description: The transaction description, already cleaned.
        from_account: The account that decreases.
        to_account: The account that increases.
        amount: The amount in from_account's currency, which is also the
            transaction currency.
        to_quantity: The amount in to_account's commodity; equal to amount
            when both accounts share a currency.
    """

    post_date: datetime.date
    description: str
    from_account: accounts.Account
    to_account: accounts.Account
    amount: money.Rational
    to_quantity: money.Rational


def clean_description(text: str) -> str:
    """Trims a description and turns each run of line breaks and tabs into a space.

    Raises:
        EntryError: The cleaned text is longer than the column allows.
    """
    cleaned = _BREAKS.sub(" ", text).strip()
    if len(cleaned) > _DESCRIPTION_MAX:
        raise EntryError(
            f"The description allows at most {_DESCRIPTION_MAX} characters."
        )
    return cleaned


def _guid() -> str:
    return uuid.uuid4().hex


def build(
    expense: Expense, now: datetime.datetime
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Builds the transaction row and its two split rows.

    Args:
        expense: The expense to record.
        now: The entry time, timezone-aware.

    Returns:
        The transactions row and the splits rows, decrease first, as column
        names mapped to values. Times are aware datetimes in UTC.

    Raises:
        ValueError: `now` has no time zone.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tx_guid = _guid()
    transaction: dict[str, object] = {
        "guid": tx_guid,
        "currency_guid": expense.from_account.commodity_guid,
        "num": "",
        "post_date": datetime.datetime.combine(expense.post_date, _POST_TIME),
        "enter_date": now.astimezone(datetime.UTC),
        "description": expense.description,
    }
    amount = expense.amount

    def split(
        account: accounts.Account, value: money.Rational, quantity: money.Rational
    ) -> dict[str, object]:
        return {
            "guid": _guid(),
            "tx_guid": tx_guid,
            "account_guid": account.guid,
            "memo": "",
            "action": "",
            "reconcile_state": "n",
            "reconcile_date": None,
            "value_num": value.num,
            "value_denom": value.denom,
            "quantity_num": quantity.num,
            "quantity_denom": quantity.denom,
            "lot_guid": None,
        }

    negative = money.Rational(-amount.num, amount.denom)
    splits = [
        split(expense.from_account, negative, negative),
        split(expense.to_account, amount, expense.to_quantity),
    ]
    return transaction, splits


def _naive_utc(row: dict[str, object]) -> dict[str, object]:
    """Drops the zone from UTC times, as GnuCash stores timestamps."""
    return {
        k: v.astimezone(datetime.UTC).replace(tzinfo=None)
        if isinstance(v, datetime.datetime)
        else v
        for k, v in row.items()
    }


def insert(conn: psycopg.Connection, expense: Expense) -> str:
    """Inserts an expense and commits it.

    Reads the caller made on the same connection, such as the account
    lookup, leave it inside an implicit transaction, where
    conn.transaction() only opens a savepoint; the final commit makes the
    rows durable either way. The caller must not have uncommitted writes
    of its own on the connection.

    Returns:
        The GUID of the new transaction.
    """
    transaction, splits = build(expense, datetime.datetime.now(datetime.UTC))
    # Naive values go out as timestamp without time zone, so the session
    # time zone does not shift them.
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(_TRANSACTION_SQL, _naive_utc(transaction))
        cur.executemany(_SPLIT_SQL, [_naive_utc(s) for s in splits])
    conn.commit()
    return str(transaction["guid"])
