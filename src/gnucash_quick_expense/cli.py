"""The gnucash-quick-expense command, which serves the form over HTTP."""

import argparse
import os
import pathlib
from collections.abc import Sequence

import uvicorn

from gnucash_quick_expense import app
from gnucash_quick_expense import config
from gnucash_quick_expense import db


def main(argv: Sequence[str] | None = None) -> None:
    """Serves the form until interrupted.

    The database location comes from the GQE_DB_* environment variables.
    TLS is left to a reverse proxy in front of the server.
    """
    parser = argparse.ArgumentParser(
        description="Serve a web form that adds one expense to a GnuCash database."
    )
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on")
    parser.add_argument("--port", type=int, default=8082, help="port to listen on")
    parser.add_argument(
        "--config",
        default=os.environ.get("GQE_CONFIG"),
        help="YAML file of account lists (default: $GQE_CONFIG)",
    )
    args = parser.parse_args(argv)
    if not args.config:
        parser.error("--config or GQE_CONFIG is required")
    try:
        cfg = config.load(pathlib.Path(args.config))
        settings = db.Settings.from_env(os.environ)
    except (OSError, ValueError) as e:
        parser.error(str(e))
    uvicorn.run(
        app.create_app(cfg, settings),
        host=args.host,
        port=args.port,
        access_log=False,
        proxy_headers=False,
        server_header=False,
    )
