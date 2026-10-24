"""SQLite access using the per-request `g` pattern from the Flask docs."""
import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext

SCHEMA = """
CREATE TABLE IF NOT EXISTS task (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT NOT NULL,
    status  TEXT NOT NULL DEFAULT 'todo',
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    get_db().executescript(SCHEMA)


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create the tables (safe to run repeatedly)."""
    init_db()
    click.echo("Database ready.")


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
