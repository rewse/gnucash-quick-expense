# gnucash-quick-expense

A small web form for adding one expense at a time to a [GnuCash](https://www.gnucash.org/) book stored in PostgreSQL, built for entering a purchase on a phone right after paying. It writes one transaction with two splits, from an asset account such as cash into an expense account. It does not provide the features of GnuCash itself: it cannot show, edit, or delete transactions, and it handles no other kind of entry.

## How it works

You sign in with a PostgreSQL username and password. The server uses them to read the accounts table and offers two lists: the accounts the money comes from and the expense accounts it goes to. Both lists are built from patterns in a configuration file. You enter the amount, choose the accounts, and optionally change the date (today by default) and add a description. **Add** inserts the transaction at once, without a confirmation step, and signs you out.

When the two accounts use different currencies, for example US dollar cash paid into an expense account in Japanese yen, the form asks for the amount in the expense account's currency and fills it in for you:

- For a yen expense account, it uses the TTM (middle rate) that MUFG Bank publishes on [murc-kawasesouba.jp](https://www.murc-kawasesouba.jp/fx/past_3month.php). On weekends and holidays it uses the last earlier business day.
- When MUFG does not publish the currency, or the site cannot be reached, it uses the newest price on or before the date in the GnuCash price database, in either direction.
- When neither has a rate, you enter the amount yourself.

The form shows where the rate came from and its date, and you can overwrite the amount before adding.

Amounts are handled as integer numerators and denominators, as GnuCash stores them, and never as floating point. Each transaction's date is stored at 10:59 UTC, the time GnuCash itself uses for date-only entries. Both splits are left unreconciled (`n`).

## Requirements

- Python 3.12 or later and [uv](https://docs.astral.sh/uv/)
- A GnuCash book in PostgreSQL
- A reverse proxy that terminates TLS in front of the server

Give the form its own PostgreSQL role that can read accounts and prices and insert transactions, and nothing else:

```sql
CREATE ROLE "expense-form" LOGIN PASSWORD '...' CONNECTION LIMIT 5;
GRANT CONNECT ON DATABASE gnucash TO "expense-form";
GRANT USAGE ON SCHEMA public TO "expense-form";
GRANT SELECT ON accounts, commodities, prices TO "expense-form";
GRANT INSERT ON transactions, splits TO "expense-form";
```

## Configuration

Copy [`config.example.yaml`](config.example.yaml) and list the account paths to offer, without the leading `Root Account:`. In a pattern, `*` matches one account name and `**` matches one or more. Placeholder and hidden accounts are never offered.

```yaml
from_accounts:
  patterns:
    - "Assets:**:Cash"
  default: "Assets:Current Assets:Cash"
to_accounts:
  patterns:
    - "Expenses:**"
  default: "Expenses:Dining"
```

The database location comes from environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `GQE_CONFIG` | | Path to the configuration file, if `--config` is not given |
| `GQE_DB_HOST` | | Database host |
| `GQE_DB_NAME` | | Database name |
| `GQE_DB_PORT` | `5432` | Database port |
| `GQE_DB_SSLMODE` | `require` | libpq `sslmode` |
| `GQE_DB_SSLROOTCERT` | | CA bundle for `verify-ca` or `verify-full` |

## Running

```sh
uv sync --frozen
GQE_DB_HOST=db.example.com GQE_DB_NAME=gnucash \
  uv run gnucash-quick-expense --config config.yaml
```

The server listens on `127.0.0.1:8082`; change it with `--host` and `--port`. Put it behind a reverse proxy that serves HTTPS.

## Security

The username and password travel with every request, over HTTPS, in the request body. The server uses them for that request's database connection and keeps nothing: no session, no cookie, and nothing in browser storage or the logs. The page forgets the password after each expense.

A rejected login answers HTTP 401 on `POST /api/*`, so a tool such as fail2ban can ban repeated failures from the proxy's access log. Every response carries a strict Content Security Policy.

## Development

```sh
uv sync --extra test
uv run pytest
```

The tests under `tests/integration` need a disposable PostgreSQL server and are skipped otherwise:

```sh
docker run -d --name gqe-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16
GQE_TEST_DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres uv run pytest
```

## License

[MIT](LICENSE)
