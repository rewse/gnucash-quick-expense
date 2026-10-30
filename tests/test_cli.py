import pathlib

import pytest
import uvicorn

from gnucash_quick_expense import cli

EXAMPLE = pathlib.Path(__file__).resolve().parents[1] / "config.example.yaml"
DB_ENV = {"GQE_DB_HOST": "db.example.com", "GQE_DB_NAME": "gnucash"}


@pytest.fixture
def runs(monkeypatch):
    recorded = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: recorded.append(kwargs))
    for key, value in DB_ENV.items():
        monkeypatch.setenv(key, value)
    return recorded


def test_main_serves_on_loopback_by_default(runs, monkeypatch):
    monkeypatch.setenv("GQE_CONFIG", str(EXAMPLE))
    cli.main([])
    (kwargs,) = runs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8082
    assert kwargs["access_log"] is False
    assert kwargs["proxy_headers"] is False
    assert kwargs["server_header"] is False


def test_main_reads_arguments(runs, monkeypatch):
    monkeypatch.delenv("GQE_CONFIG", raising=False)
    cli.main(["--host", "::1", "--port", "9000", "--config", str(EXAMPLE)])
    (kwargs,) = runs
    assert (kwargs["host"], kwargs["port"]) == ("::1", 9000)


def test_main_requires_a_config(runs, monkeypatch):
    monkeypatch.delenv("GQE_CONFIG", raising=False)
    with pytest.raises(SystemExit):
        cli.main([])
    assert runs == []


def test_main_rejects_an_invalid_config(runs, monkeypatch, tmp_path):
    bad = tmp_path / "config.yaml"
    bad.write_text("- not a mapping\n")
    with pytest.raises(SystemExit):
        cli.main(["--config", str(bad)])
    assert runs == []


def test_main_requires_database_settings(runs, monkeypatch):
    monkeypatch.delenv("GQE_DB_HOST")
    with pytest.raises(SystemExit):
        cli.main(["--config", str(EXAMPLE)])
    assert runs == []
