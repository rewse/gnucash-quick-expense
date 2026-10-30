"""Account paths from the GnuCash accounts table and the lists offered."""

from typing import NamedTuple

import psycopg

from gnucash_quick_expense import config

# Paths start below "Root Account". GnuCash keeps scheduled-transaction
# templates under a second root, "Template Root", which is left out.
_ACCOUNTS_SQL = """
WITH RECURSIVE tree AS (
    SELECT a.guid, a.name::text AS path, a.commodity_guid, a.hidden, a.placeholder
    FROM accounts a
    JOIN accounts root ON root.guid = a.parent_guid
    WHERE root.parent_guid IS NULL AND root.name = 'Root Account'
    UNION ALL
    SELECT c.guid, tree.path || ':' || c.name, c.commodity_guid, c.hidden, c.placeholder
    FROM accounts c
    JOIN tree ON tree.guid = c.parent_guid
)
SELECT tree.guid, tree.path, tree.commodity_guid, cm.mnemonic, cm.fraction,
       COALESCE(tree.hidden, 0) = 0 AND COALESCE(tree.placeholder, 0) = 0
FROM tree
JOIN commodities cm ON cm.guid = tree.commodity_guid
"""


class Account(NamedTuple):
    """A GnuCash account with its full path and commodity."""

    guid: str
    path: str
    commodity_guid: str
    mnemonic: str
    fraction: int
    usable: bool


def fetch_all(conn: psycopg.Connection) -> list[Account]:
    """Reads every account under Root Account that has a commodity."""
    with conn.cursor() as cur:
        cur.execute(_ACCOUNTS_SQL)
        return [Account(*row) for row in cur.fetchall()]


def choose(all_accounts: list[Account], choice: config.AccountChoice) -> list[Account]:
    """Returns the usable accounts that match a choice, sorted by path."""
    return sorted(
        (
            a
            for a in all_accounts
            if a.usable and any(config.matches(p, a.path) for p in choice.patterns)
        ),
        key=lambda a: a.path,
    )


def default_path(choices: list[Account], choice: config.AccountChoice) -> str | None:
    """Returns the configured default when it is among the choices."""
    if choice.default in {a.path for a in choices}:
        return choice.default
    return None
