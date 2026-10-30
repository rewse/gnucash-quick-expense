# AGENTS.md

## Product

gnucash-quick-expense is a web form that adds one expense at a time to a GnuCash book in PostgreSQL: one transaction with two splits, from an asset account into an expense account. It offers no reading, editing, or deletion, and the README must not suggest it replaces GnuCash. `docs/superpowers/specs/2026-10-31-gnucash-quick-expense-design.md` records the design decisions.

The repository is public. Keep personal account names, host names, and database endpoints out of the code, tests, and documents; deployments pass them through `config.yaml` and the `GQE_DB_*` variables. The maintainer's deployment lives in `rewse/ansible-playbooks` (role `gnucash_quick_expense`).

## Rules that protect the books and the credentials

- Never use floats for amounts, in Python or JavaScript. Amounts are strings until `money.parse_amount` turns them into integer numerators over the commodity's fraction.
- Never log, echo, or store the PostgreSQL credentials. psycopg's `OperationalError` carries the password in its `pgconn` repr, so log only exception types and never chain a connect error.
- A rejected login is HTTP 401 on `POST /api/*`; fail2ban relies on it. Input errors are 400 (415 when the Content-Type is not application/json, 413 for a body over 16 KiB), everything else 500 without details.
- Take account paths from the client and resolve them against the server-built choices; never accept a GUID from the client.
- Keep the page free of inline scripts, style attributes, and remote resources so the CSP stays at `'self'`.

## Development

Use uv, not pip. Run `uv sync --extra test`, then `uv run pytest`. The integration tests need `GQE_TEST_DATABASE_URL` pointing at a disposable PostgreSQL 16, because they drop and recreate the GnuCash tables; on macOS start one with `container run -d --name gqe-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16`. Check UI changes in a phone-sized browser against that database before committing.

Follow the Google Python Style Guide, including importing modules rather than classes or functions (`from gnucash_quick_expense import money`). Order CSS properties outside-in (Concentric-CSS).

## Dependencies and security

A new dependency or version must be at least 96 hours old, maintained, and free of known vulnerabilities. `[tool.uv] exclude-newer = "4 days"` enforces the age for every resolution; keep it. Run `uv lock` with an empty user configuration (`XDG_CONFIG_HOME=$(mktemp -d /tmp/uvcfg.XXXXXX) uv lock`) so user-level settings do not leak into `uv.lock`. Before committing a dependency change, run `osv-scanner --lockfile=uv.lock` and the tests.

Report vulnerabilities through a GitHub Security Advisory, not a public issue.

## Commits

Use Conventional Commits with a body that explains what changed and why. Use the module name as the scope: `accounts`, `app`, `cli`, `config`, `db`, `ledger`, `money`, `rates`, or `web` for the static files.

## Validation

Before pushing, stage new files and run `uvx --with pre-commit-uv==4.3.0 pre-commit@4.6.2 run --all-files` and `uv run pytest` with `GQE_TEST_DATABASE_URL` set. Commit any files the hooks reformat.
