import datetime
import os

import psycopg

from gnucash_quick_expense import accounts
from gnucash_quick_expense import ledger
from gnucash_quick_expense import money


def _by_path(conn) -> dict[str, accounts.Account]:
    return {a.path: a for a in accounts.fetch_all(conn)}


def _expense(found: dict[str, accounts.Account]) -> ledger.Expense:
    return ledger.Expense(
        post_date=datetime.date(2026, 10, 30),
        description="Lunch",
        from_account=found["Assets:Dollar:Cash"],
        to_account=found["Expenses:Food:Dining"],
        amount=money.Rational(1250, 100),
        to_quantity=money.Rational(1969, 1),
    )


def test_insert_writes_one_balanced_transaction(gnucash_db):
    found = _by_path(gnucash_db)
    tx_guid = ledger.insert(gnucash_db, _expense(found))

    with gnucash_db.cursor() as cur:
        cur.execute(
            "SELECT post_date, enter_date, description, currency_guid FROM transactions"
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT account_guid, value_num, value_denom, quantity_num, quantity_denom,"
            " reconcile_state FROM splits WHERE tx_guid = %s ORDER BY value_num",
            (tx_guid,),
        )
        splits = cur.fetchall()

    assert len(rows) == 1
    post_date, enter_date, description, currency_guid = rows[0]
    assert post_date == datetime.datetime(2026, 10, 30, 10, 59)
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    assert abs(now - enter_date) < datetime.timedelta(minutes=1)
    assert description == "Lunch"
    assert currency_guid == found["Assets:Dollar:Cash"].commodity_guid
    assert splits == [
        (found["Assets:Dollar:Cash"].guid, -1250, 100, -1250, 100, "n"),
        (found["Expenses:Food:Dining"].guid, 1250, 100, 1969, 1, "n"),
    ]
    assert sum(s[1] for s in splits) == 0


def test_insert_commits_after_reads_on_the_same_connection(gnucash_db):
    # fetch_all leaves the connection inside an implicit transaction, as the
    # API does before it inserts.
    found = _by_path(gnucash_db)
    tx_guid = ledger.insert(gnucash_db, _expense(found))

    with psycopg.connect(os.environ["GQE_TEST_DATABASE_URL"]) as other:
        count = other.execute(
            "SELECT count(*) FROM splits WHERE tx_guid = %s", (tx_guid,)
        ).fetchone()
    assert count == (2,)
