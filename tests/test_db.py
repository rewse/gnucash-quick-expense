import pytest

from gnucash_quick_expense import db


def test_settings_from_env_defaults():
    settings = db.Settings.from_env(
        {"GQE_DB_HOST": "db.example.com", "GQE_DB_NAME": "gnucash"}
    )
    assert settings == db.Settings("db.example.com", 5432, "gnucash", "require", None)


def test_settings_from_env_reads_every_variable():
    settings = db.Settings.from_env(
        {
            "GQE_DB_HOST": "db.example.com",
            "GQE_DB_PORT": "6543",
            "GQE_DB_NAME": "books",
            "GQE_DB_SSLMODE": "verify-ca",
            "GQE_DB_SSLROOTCERT": "/etc/ssl/rds.pem",
        }
    )
    assert settings == db.Settings(
        "db.example.com", 6543, "books", "verify-ca", "/etc/ssl/rds.pem"
    )


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"GQE_DB_HOST": "h"},
        {"GQE_DB_NAME": "n"},
        {"GQE_DB_HOST": "h", "GQE_DB_NAME": "n", "GQE_DB_PORT": "x"},
    ],
    ids=["empty", "no-name", "no-host", "bad-port"],
)
def test_settings_from_env_rejects_incomplete_settings(environ):
    with pytest.raises(ValueError):
        db.Settings.from_env(environ)
