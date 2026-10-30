import datetime
import decimal
import logging
import typing

import httpx
import psycopg
import pytest
from starlette import testclient

from gnucash_quick_expense import accounts
from gnucash_quick_expense import app
from gnucash_quick_expense import config
from gnucash_quick_expense import db
from gnucash_quick_expense import ledger
from gnucash_quick_expense import money
from gnucash_quick_expense import rates

PASSWORD = "s3cret-Passw0rd"
JPY, TWD, USD = "c-jpy", "c-twd", "c-usd"


def _account(guid, path, commodity, mnemonic, fraction, usable=True):
    return accounts.Account(guid, path, commodity, mnemonic, fraction, usable)


ALL = [
    _account("g-jpy", "Assets:Yen:Cash", JPY, "JPY", 1),
    _account("g-twd", "Assets:NT Dollar:Cash", TWD, "TWD", 100),
    _account("g-usd", "Assets:Dollar:Cash", USD, "USD", 100),
    _account("g-dining", "Expenses:Food:Dining", JPY, "JPY", 1),
    _account("g-taxi", "Expenses:Transport:Taxi", JPY, "JPY", 1),
    _account("g-old", "Expenses:Old", JPY, "JPY", 1, usable=False),
]
CONFIG = config.Config(
    config.AccountChoice(("Assets:**:Cash",), "Assets:Yen:Cash"),
    config.AccountChoice(("Expenses:**",), "Expenses:Food:Dining"),
)
SETTINGS = db.Settings("db.invalid", 5432, "gnucash", "require", None)


class _Conn:
    closed = False

    def close(self):
        self.closed = True


class _Murc(rates.MurcClient):
    """Answers every request with one quote, without the network."""

    def __init__(self, quote=None):
        self.quote = quote
        self.calls = []

    async def ttm(self, currency, on):
        self.calls.append((currency, on))
        return self.quote


@pytest.fixture
def calls(monkeypatch):
    recorded = {"insert": [], "price": [], "connections": []}
    monkeypatch.setattr(accounts, "fetch_all", lambda conn: list(ALL))

    def insert(conn, expense):
        recorded["insert"].append(expense)
        return "0123456789abcdef0123456789abcdef"

    monkeypatch.setattr(ledger, "insert", insert)

    def price(conn, commodity_guid, currency_guid, on):
        recorded["price"].append((commodity_guid, currency_guid, on))
        return recorded.get("price_quote")

    monkeypatch.setattr(rates, "gnucash_price", price)
    return recorded


def _connect_for(recorded):
    def connect(settings, user, password):
        if user == "bad" or password != PASSWORD:
            raise db.AuthError()
        conn = _Conn()
        recorded["connections"].append(conn)
        return typing.cast(psycopg.Connection, conn)

    return connect


def _client(recorded, murc=None) -> testclient.TestClient:
    application = app.create_app(
        CONFIG, SETTINGS, connect=_connect_for(recorded), murc=murc or _Murc()
    )
    return testclient.TestClient(application)


def _post(client, path, **body):
    body.setdefault("username", "expense-form")
    body.setdefault("password", PASSWORD)
    return client.post(path, json=body)


def test_accounts_returns_choices_and_defaults(calls):
    response = _post(_client(calls), "/api/accounts")
    assert response.status_code == 200
    assert response.json() == {
        "from": [
            {"path": "Assets:Dollar:Cash", "currency": "USD"},
            {"path": "Assets:NT Dollar:Cash", "currency": "TWD"},
            {"path": "Assets:Yen:Cash", "currency": "JPY"},
        ],
        "to": [
            {"path": "Expenses:Food:Dining", "currency": "JPY"},
            {"path": "Expenses:Transport:Taxi", "currency": "JPY"},
        ],
        "from_default": "Assets:Yen:Cash",
        "to_default": "Expenses:Food:Dining",
    }
    assert all(c.closed for c in calls["connections"])


@pytest.mark.parametrize("path", ["/api/accounts", "/api/rate", "/api/expenses"])
def test_wrong_password_is_401(calls, path):
    response = _post(
        _client(calls),
        path,
        password="wrong-" + PASSWORD,
        **{"from": "Assets:Dollar:Cash", "to": "Expenses:Food:Dining"},
        date="2026-10-30",
        amount="1",
        description="",
    )
    assert response.status_code == 401
    assert response.json() == {"error": "Wrong username or password."}
    assert PASSWORD not in response.text


@pytest.mark.parametrize("path", ["/api/accounts", "/api/rate", "/api/expenses"])
def test_non_json_is_415(calls, path):
    response = _client(calls).post(path, data={"username": "u", "password": PASSWORD})
    assert response.status_code == 415


@pytest.mark.parametrize(
    "body",
    [b"[]", b"{", b'{"username": 1, "password": "x"}', b'{"username": "u"}'],
    ids=["not-an-object", "invalid-json", "non-string", "missing-password"],
)
def test_malformed_body_is_400(calls, body):
    response = _client(calls).post(
        "/api/accounts", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_oversized_body_is_413(calls):
    response = _post(_client(calls), "/api/accounts", description="x" * 17000)
    assert response.status_code == 413


def _expense_body(**overrides):
    body = {
        "from": "Assets:Yen:Cash",
        "to": "Expenses:Food:Dining",
        "date": "2026-10-30",
        "description": "Lunch",
        "amount": "1200",
        "to_amount": "",
    }
    body.update(overrides)
    return body


def test_expense_in_one_currency(calls):
    response = _post(_client(calls), "/api/expenses", **_expense_body())
    assert response.status_code == 200
    assert response.json() == {
        "guid": "0123456789abcdef0123456789abcdef",
        "date": "2026-10-30",
        "amount": "1200",
        "currency": "JPY",
        "from": "Assets:Yen:Cash",
        "to": "Expenses:Food:Dining",
        "to_amount": "1200",
        "to_currency": "JPY",
    }
    (expense,) = calls["insert"]
    assert expense.post_date == datetime.date(2026, 10, 30)
    assert expense.description == "Lunch"
    assert expense.amount == expense.to_quantity == money.Rational(1200, 1)
    assert expense.from_account.guid == "g-jpy"
    assert expense.to_account.guid == "g-dining"
    assert all(c.closed for c in calls["connections"])


@pytest.mark.parametrize(
    "to",
    ["expenses:foods:dining", "Expenses:Food:Dining ", "Expenses:Old", "Expenses"],
)
def test_unknown_to_account_is_400_and_inserts_nothing(calls, to):
    response = _post(_client(calls), "/api/expenses", **_expense_body(to=to))
    assert response.status_code == 400
    assert calls["insert"] == []


def test_unknown_from_account_is_400(calls):
    response = _post(
        _client(calls),
        "/api/expenses",
        **_expense_body(**{"from": "Expenses:Food:Dining"}),
    )
    assert response.status_code == 400
    assert calls["insert"] == []


def test_ambiguous_account_path_is_400(calls, monkeypatch):
    twin = _account("g-dining-2", "Expenses:Food:Dining", JPY, "JPY", 1)
    monkeypatch.setattr(accounts, "fetch_all", lambda conn: [*ALL, twin])
    response = _post(_client(calls), "/api/expenses", **_expense_body())
    assert response.status_code == 400
    assert calls["insert"] == []


def test_foreign_expense_requires_to_amount(calls):
    client = _client(calls)
    body = _expense_body(**{"from": "Assets:Dollar:Cash"}, amount="12.50")
    assert _post(client, "/api/expenses", **body).status_code == 400
    assert (
        _post(client, "/api/expenses", **{**body, "to_amount": "0"}).status_code == 400
    )
    response = _post(client, "/api/expenses", **{**body, "to_amount": "1969"})
    assert response.status_code == 200
    assert response.json()["amount"] == "12.50"
    assert response.json()["currency"] == "USD"
    assert response.json()["to_amount"] == "1969"
    (expense,) = calls["insert"]
    assert expense.amount == money.Rational(1250, 100)
    assert expense.to_quantity == money.Rational(1969, 1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "0"},
        {"amount": "1.5"},
        {"amount": "1e3"},
        {"amount": "１２００"},
        {"description": "x" * 2049},
        {"date": "2026-02-30"},
        {"date": "2026/10/30"},
        {"date": ""},
    ],
    ids=[
        "zero",
        "jpy-decimals",
        "exponent",
        "full-width",
        "long-description",
        "no-such-day",
        "slashes",
        "empty-date",
    ],
)
def test_invalid_expense_is_400(calls, overrides):
    response = _post(_client(calls), "/api/expenses", **_expense_body(**overrides))
    assert response.status_code == 400
    assert response.json()["error"]
    assert calls["insert"] == []


def _rate_body(**overrides):
    body = {
        "from": "Assets:Dollar:Cash",
        "to": "Expenses:Food:Dining",
        "date": "2026-10-31",
        "amount": "12.50",
    }
    body.update(overrides)
    return body


def test_rate_uses_mufg_ttm(calls):
    murc = _Murc(
        rates.Quote(decimal.Decimal("157.54"), datetime.date(2026, 10, 30), "MUFG TTM")
    )
    response = _post(_client(calls, murc), "/api/rate", **_rate_body())
    assert response.status_code == 200
    assert response.json() == {
        "to_amount": "1969",
        "rate": "157.54",
        "rate_date": "2026-10-30",
        "source": "MUFG TTM",
    }
    assert murc.calls == [("USD", datetime.date(2026, 10, 31))]
    assert calls["price"] == []


def test_rate_falls_back_to_gnucash_price(calls):
    calls["price_quote"] = rates.Quote(
        decimal.Decimal("4.87"), datetime.date(2026, 8, 6), "GnuCash price"
    )
    response = _post(
        _client(calls),
        "/api/rate",
        **_rate_body(**{"from": "Assets:NT Dollar:Cash"}, amount="3965"),
    )
    assert response.status_code == 200
    assert response.json() == {
        "to_amount": "19310",
        "rate": "4.87",
        "rate_date": "2026-08-06",
        "source": "GnuCash price",
    }
    assert calls["price"] == [(TWD, JPY, datetime.date(2026, 10, 31))]


def test_rate_uses_gnucash_price_when_the_site_fails(calls):
    def fail(request):
        raise httpx.ConnectTimeout("timed out")

    murc = rates.MurcClient(
        httpx.AsyncClient(transport=httpx.MockTransport(fail)), max_days_back=0
    )
    calls["price_quote"] = rates.Quote(
        decimal.Decimal(150), datetime.date(2026, 7, 31), "GnuCash price"
    )
    response = _post(_client(calls, murc), "/api/rate", **_rate_body())
    assert response.status_code == 200
    assert response.json()["to_amount"] == "1875"
    assert response.json()["source"] == "GnuCash price"


def test_rate_is_empty_only_without_any_rate(calls):
    response = _post(_client(calls), "/api/rate", **_rate_body())
    assert response.status_code == 200
    assert response.json() == {
        "to_amount": None,
        "rate": None,
        "rate_date": None,
        "source": None,
    }


def test_rate_too_small_to_convert_leaves_the_amount_empty(calls):
    murc = _Murc(
        rates.Quote(decimal.Decimal("0.1177"), datetime.date(2026, 10, 30), "MUFG TTM")
    )
    response = _post(_client(calls, murc), "/api/rate", **_rate_body(amount="0.01"))
    assert response.status_code == 200
    assert response.json()["to_amount"] is None
    assert response.json()["rate"] == "0.1177"


def test_rate_for_one_currency_is_400(calls):
    response = _post(
        _client(calls),
        "/api/rate",
        **_rate_body(**{"from": "Assets:Yen:Cash"}, amount="1200"),
    )
    assert response.status_code == 400


@pytest.mark.parametrize("date", ["2026-02-30", "2026/10/30"])
def test_invalid_date_is_400(calls, date):
    response = _post(_client(calls), "/api/rate", **_rate_body(date=date))
    assert response.status_code == 400


def test_database_failure_is_500_without_details(calls, monkeypatch):
    def broken(conn):
        raise RuntimeError("connection to db.invalid failed")

    monkeypatch.setattr(accounts, "fetch_all", broken)
    client = testclient.TestClient(
        app.create_app(CONFIG, SETTINGS, connect=_connect_for(calls), murc=_Murc()),
        raise_server_exceptions=False,
    )
    response = _post(client, "/api/accounts")
    assert response.status_code == 500
    assert "db.invalid" not in response.text


def test_security_headers(calls):
    client = _client(calls)
    for response in (client.get("/"), _post(client, "/api/accounts")):
        assert response.headers["content-security-policy"] == (
            "default-src 'self'; frame-ancestors 'none'; base-uri 'none';"
            " form-action 'self'"
        )
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"


def test_static_files_are_versioned_and_cached(calls):
    client = _client(calls)
    page = client.get("/").text
    for name in ("app.js", "app.css"):
        marker = f"/static/{name}?v="
        assert marker in page
        version = page.split(marker, 1)[1].split('"', 1)[0]
        assert len(version) >= 8
        response = client.get(f"/static/{name}?v={version}")
        assert response.status_code == 200
        assert (
            response.headers["cache-control"] == "public, max-age=31536000, immutable"
        )
        assert response.headers["content-security-policy"]


def test_unknown_static_file_is_404(calls):
    client = _client(calls)
    assert client.get("/static/index.html").status_code == 404
    assert client.get("/static/../app.py").status_code == 404


def test_logs_do_not_contain_credentials(calls, caplog):
    caplog.set_level(logging.DEBUG)
    client = _client(calls)
    _post(client, "/api/accounts")
    _post(client, "/api/accounts", password="wrong")
    _post(client, "/api/rate", **_rate_body())
    _post(client, "/api/expenses", **_expense_body())
    assert PASSWORD not in caplog.text
