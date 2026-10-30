"""The web application: one page and three JSON APIs.

Every API request carries the PostgreSQL username and password, opens its
own connection with them, and closes it before responding. Nothing about
the credentials is kept, logged, or echoed.
"""

import contextlib
import datetime
import hashlib
import json
import logging
import pathlib
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import psycopg
from starlette import applications
from starlette import concurrency
from starlette import middleware
from starlette import requests
from starlette import responses
from starlette import routing
from starlette import types

from gnucash_quick_expense import accounts
from gnucash_quick_expense import config
from gnucash_quick_expense import db
from gnucash_quick_expense import ledger
from gnucash_quick_expense import money
from gnucash_quick_expense import rates

_log = logging.getLogger(__name__)

_STATIC = pathlib.Path(__file__).with_name("static")
_ASSETS = {
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}
_MAX_BODY = 16 * 1024
_JPY = "JPY"

_SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; frame-ancestors 'none'; base-uri 'none';"
        " form-action 'self'"
    ),
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
}
_NO_STORE = "no-store"
_IMMUTABLE = "public, max-age=31536000, immutable"

Connect = Callable[[db.Settings, str, str], psycopg.Connection]


class _BadRequest(Exception):
    """A request the client must change; the message is shown to the user."""


class _TooLarge(Exception):
    """A request body over the size limit."""


class _Unsupported(Exception):
    """A request body that is not JSON."""


def _json(body: dict[str, Any], status: int = 200) -> responses.JSONResponse:
    return responses.JSONResponse(body, status, headers={"cache-control": _NO_STORE})


def _error(message: str, status: int) -> responses.JSONResponse:
    return _json({"error": message}, status)


async def _body(request: requests.Request) -> dict[str, Any]:
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise _Unsupported()
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > _MAX_BODY:
            raise _TooLarge()
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise _BadRequest("The request is not valid JSON.") from e
    if not isinstance(data, dict):
        raise _BadRequest("The request must be a JSON object.")
    return data


def _text(data: dict[str, Any], key: str, required: bool = True) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise _BadRequest(f"{key} must be a string.")
    if required and not value:
        raise _BadRequest(f"{key} is required.")
    return value


def _date(text: str) -> datetime.date:
    try:
        if len(text) != 10:
            raise ValueError(text)
        return datetime.date.fromisoformat(text)
    except ValueError as e:
        raise _BadRequest("Enter the date as YYYY-MM-DD.") from e


def _resolve(
    choices: list[accounts.Account], path: str, label: str
) -> accounts.Account:
    found = [a for a in choices if a.path == path]
    if not found:
        raise _BadRequest(f"Choose a {label} account from the list.")
    if len(found) > 1:
        raise _BadRequest(f"More than one {label} account is named {path}.")
    return found[0]


def _listing(choices: list[accounts.Account]) -> list[dict[str, str]]:
    return [{"path": a.path, "currency": a.mnemonic} for a in choices]


class _Session:
    """One request's connection and the account lists built from it."""

    def __init__(self, conn: psycopg.Connection, cfg: config.Config) -> None:
        self.conn = conn
        everything = accounts.fetch_all(conn)
        self.from_choices = accounts.choose(everything, cfg.from_accounts)
        self.to_choices = accounts.choose(everything, cfg.to_accounts)

    def pair(self, data: dict[str, Any]) -> tuple[accounts.Account, accounts.Account]:
        source = _resolve(self.from_choices, _text(data, "from"), "From")
        target = _resolve(self.to_choices, _text(data, "to"), "To")
        return source, target


def create_app(
    cfg: config.Config,
    settings: db.Settings,
    connect: Connect = db.connect,
    murc: rates.MurcClient | None = None,
) -> applications.Starlette:
    """Builds the application.

    Args:
        cfg: The account lists to offer.
        settings: Where the GnuCash database is.
        connect: Opens a connection with a request's credentials.
        murc: The MUFG rate client. When None, one is created for the
            application's lifetime.
    """
    state: dict[str, rates.MurcClient] = {}
    if murc is not None:
        state["murc"] = murc

    index = (_STATIC / "index.html").read_text(encoding="utf-8")
    assets = {name: (_STATIC / name).read_bytes() for name in _ASSETS}
    for name, content in assets.items():
        version = hashlib.sha256(content).hexdigest()[:16]
        index = index.replace(f'"/static/{name}"', f'"/static/{name}?v={version}"')

    async def with_session(
        request: requests.Request,
        handle: Callable[[_Session, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> responses.Response:
        try:
            data = await _body(request)
            user, password = _text(data, "username"), _text(data, "password")
            conn = await concurrency.run_in_threadpool(
                connect, settings, user, password
            )
            try:
                session = await concurrency.run_in_threadpool(_Session, conn, cfg)
                return _json(await handle(session, data))
            finally:
                await concurrency.run_in_threadpool(conn.close)
        except db.AuthError:
            return _error("Wrong username or password.", 401)
        except _Unsupported:
            return _error("Send the request as application/json.", 415)
        except _TooLarge:
            return _error("The request is too large.", 413)
        except (_BadRequest, money.AmountError, ledger.EntryError) as e:
            return _error(str(e), 400)
        except Exception as e:  # noqa: BLE001 - every other failure must become a generic 500
            # Only the type is
            # logged, because a psycopg error's repr can include the password.
            _log.error("%s failed: %s", request.url.path, type(e).__name__)
            return _error("The request failed. Try again.", 500)

    async def list_accounts(session: _Session, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "from": _listing(session.from_choices),
            "to": _listing(session.to_choices),
            "from_default": accounts.default_path(
                session.from_choices, cfg.from_accounts
            ),
            "to_default": accounts.default_path(session.to_choices, cfg.to_accounts),
        }

    async def quote(
        session: _Session,
        source: accounts.Account,
        target: accounts.Account,
        on: datetime.date,
    ) -> rates.Quote | None:
        if target.mnemonic == _JPY:
            found = await state["murc"].ttm(source.mnemonic, on)
            if found is not None:
                return found
        return await concurrency.run_in_threadpool(
            rates.gnucash_price,
            session.conn,
            source.commodity_guid,
            target.commodity_guid,
            on,
        )

    async def rate(session: _Session, data: dict[str, Any]) -> dict[str, Any]:
        source, target = session.pair(data)
        if source.commodity_guid == target.commodity_guid:
            raise _BadRequest("Both accounts use the same currency.")
        on = _date(_text(data, "date"))
        amount = money.parse_amount(_text(data, "amount"), source.fraction)
        found = await quote(session, source, target, on)
        if found is None:
            return {"to_amount": None, "rate": None, "rate_date": None, "source": None}
        converted = money.convert(money.to_decimal(amount), found.rate, target.fraction)
        return {
            "to_amount": money.format_amount(converted) if converted.num > 0 else None,
            "rate": f"{found.rate:f}",
            "rate_date": found.date.isoformat(),
            "source": found.source,
        }

    async def add_expense(session: _Session, data: dict[str, Any]) -> dict[str, Any]:
        source, target = session.pair(data)
        on = _date(_text(data, "date"))
        description = ledger.clean_description(
            _text(data, "description", required=False)
        )
        amount = money.parse_amount(_text(data, "amount"), source.fraction)
        if source.commodity_guid == target.commodity_guid:
            to_quantity = amount
        else:
            text = _text(data, "to_amount", required=False)
            if not text:
                raise _BadRequest(f"Enter the amount in {target.mnemonic}.")
            to_quantity = money.parse_amount(text, target.fraction)
        expense = ledger.Expense(on, description, source, target, amount, to_quantity)
        guid = await concurrency.run_in_threadpool(ledger.insert, session.conn, expense)
        return {
            "guid": guid,
            "date": on.isoformat(),
            "amount": money.format_amount(amount),
            "currency": source.mnemonic,
            "from": source.path,
            "to": target.path,
            "to_amount": money.format_amount(to_quantity),
            "to_currency": target.mnemonic,
        }

    async def api_accounts(request: requests.Request) -> responses.Response:
        return await with_session(request, list_accounts)

    async def api_rate(request: requests.Request) -> responses.Response:
        return await with_session(request, rate)

    async def api_expenses(request: requests.Request) -> responses.Response:
        return await with_session(request, add_expense)

    async def page(request: requests.Request) -> responses.Response:
        return responses.HTMLResponse(index, headers={"cache-control": _NO_STORE})

    async def asset(request: requests.Request) -> responses.Response:
        name = request.path_params["name"]
        if name not in assets:
            return responses.PlainTextResponse(
                "Not found", 404, headers={"cache-control": _NO_STORE}
            )
        return responses.Response(
            assets[name],
            media_type=_ASSETS[name],
            headers={"cache-control": _IMMUTABLE},
        )

    @contextlib.asynccontextmanager
    async def lifespan(application: applications.Starlette):
        if "murc" in state:
            yield
            return
        async with httpx.AsyncClient() as client:
            state["murc"] = rates.MurcClient(client)
            yield
            del state["murc"]

    application = applications.Starlette(
        routes=[
            routing.Route("/", page, methods=["GET"]),
            routing.Route("/static/{name}", asset, methods=["GET"]),
            routing.Route("/api/accounts", api_accounts, methods=["POST"]),
            routing.Route("/api/rate", api_rate, methods=["POST"]),
            routing.Route("/api/expenses", api_expenses, methods=["POST"]),
        ],
        middleware=[middleware.Middleware(_SecurityHeaders)],
        lifespan=lifespan,
    )
    return application


class _SecurityHeaders:
    """Adds the security headers to every response."""

    def __init__(self, app: types.ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: types.Scope, receive: types.Receive, send: types.Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: types.Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.decode("latin-1").lower() not in _SECURITY_HEADERS
                ]
                headers += [
                    (k.encode(), v.encode()) for k, v in _SECURITY_HEADERS.items()
                ]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
