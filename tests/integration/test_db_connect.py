import os

import psycopg
import pytest
from psycopg import conninfo

from gnucash_quick_expense import db


@pytest.fixture
def server():
    """Settings for the test server and the credentials in its URL."""
    url = os.environ.get("GQE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GQE_TEST_DATABASE_URL is not set")
    info = conninfo.conninfo_to_dict(url)
    settings = db.Settings(
        str(info["host"]),
        int(info.get("port") or 5432),
        str(info["dbname"]),
        "disable",
        None,
    )
    return settings, str(info["user"]), str(info["password"])


def test_connect_reports_a_wrong_password_as_auth_error(server):
    settings, user, _ = server
    with pytest.raises(db.AuthError) as raised:
        db.connect(settings, user, "definitely-wrong")
    assert "definitely-wrong" not in repr(raised.value)
    assert "definitely-wrong" not in str(raised.value)
    # The psycopg error, whose repr carries the password, is not attached.
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_connect_reports_an_unknown_user_as_auth_error(server):
    settings, _, _ = server
    with pytest.raises(db.AuthError):
        db.connect(settings, "no-such-user", "x")


def test_connect_keeps_other_failures(server):
    settings, user, password = server
    with pytest.raises(psycopg.OperationalError):
        db.connect(settings._replace(dbname="no_such_database"), user, password)


def test_connect_returns_a_connection(server):
    settings, user, password = server
    with db.connect(settings, user, password) as conn:
        row = conn.execute("SELECT current_setting('application_name')").fetchone()
    assert row == ("gnucash-quick-expense",)
