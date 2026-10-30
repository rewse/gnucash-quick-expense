"""Fixtures for tests against a real PostgreSQL server.

Set GQE_TEST_DATABASE_URL to a disposable database to run them; schema.sql
drops and recreates the GnuCash tables there.
"""

import os
import pathlib

import psycopg
import pytest

SCHEMA = pathlib.Path(__file__).with_name("schema.sql")

JPY = "c0000000000000000000000000000jpy"
TWD = "c0000000000000000000000000000twd"
USD = "c0000000000000000000000000000usd"


@pytest.fixture
def gnucash_db():
    url = os.environ.get("GQE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GQE_TEST_DATABASE_URL is not set")
    with psycopg.connect(url) as conn:
        # bytes, because psycopg types str queries as LiteralString.
        conn.execute(SCHEMA.read_bytes())
        conn.commit()
        yield conn
