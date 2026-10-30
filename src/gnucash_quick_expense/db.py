"""Connections to the GnuCash database with the credentials a request carries."""

from collections.abc import Mapping
from typing import NamedTuple

import psycopg
from psycopg import conninfo

_APPLICATION_NAME = "gnucash-quick-expense"
_CONNECT_TIMEOUT = 10

# libpq reports no SQLSTATE for errors raised while connecting, so a failed
# login is recognized by the server's message. PostgreSQL gives the same
# message for an unknown user, so callers cannot tell the two apart.
_AUTH_FAILED = "authentication failed"


class AuthError(Exception):
    """The database rejected the username or password."""


class Settings(NamedTuple):
    """Where the database is and how to reach it."""

    host: str
    port: int
    dbname: str
    sslmode: str
    sslrootcert: str | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        """Reads GQE_DB_HOST, GQE_DB_PORT, GQE_DB_NAME, GQE_DB_SSLMODE, and
        GQE_DB_SSLROOTCERT.

        Raises:
            ValueError: The host or database name is missing, or the port is
                not a number.
        """
        host = environ.get("GQE_DB_HOST", "")
        dbname = environ.get("GQE_DB_NAME", "")
        if not host or not dbname:
            raise ValueError("GQE_DB_HOST and GQE_DB_NAME must be set")
        port = environ.get("GQE_DB_PORT", "5432")
        if not port.isdigit():
            raise ValueError(f"GQE_DB_PORT must be a number: {port!r}")
        return cls(
            host=host,
            port=int(port),
            dbname=dbname,
            sslmode=environ.get("GQE_DB_SSLMODE", "require"),
            sslrootcert=environ.get("GQE_DB_SSLROOTCERT") or None,
        )


def connect(settings: Settings, user: str, password: str) -> psycopg.Connection:
    """Opens a connection as the given user.

    Raises:
        AuthError: The username or password was rejected. The psycopg error
            is not chained, because its pgconn repr includes the password.
        psycopg.OperationalError: The database could not be reached for
            another reason.
    """
    params = {
        "host": settings.host,
        "port": str(settings.port),
        "dbname": settings.dbname,
        "user": user,
        "password": password,
        "sslmode": settings.sslmode,
        "connect_timeout": str(_CONNECT_TIMEOUT),
        "application_name": _APPLICATION_NAME,
        # sslmode=require does not authenticate the server, so a host in the
        # path could ask for a cleartext password; SCRAM never reveals it.
        "require_auth": "scram-sha-256",
    }
    if settings.sslrootcert:
        params["sslrootcert"] = settings.sslrootcert
    try:
        return psycopg.connect(conninfo.make_conninfo(**params))
    except psycopg.OperationalError as e:
        if _AUTH_FAILED not in str(e):
            raise
    # Raised outside the except block, so the psycopg error is not kept as
    # its context either.
    raise AuthError()
