"""SQLite connection handling and migrations (plan sections 3.1, M2-T01).

Stdlib ``sqlite3``, no ORM. The connection is configured the way the plan requires: WAL, foreign
keys enforced, a busy timeout, and explicit transaction boundaries rather than the driver's
implicit ones.

Schema version lives in ``PRAGMA user_version``, so migrating needs no bookkeeping table and
re-running it on an up-to-date database is a no-op.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BUSY_TIMEOUT_MS = 5000


def _migration_files() -> list[tuple[int, Path]]:
    """Migrations as ``(version, path)``, ordered by the numeric prefix of the filename."""
    found: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        prefix = path.name.split("_", 1)[0]
        if not prefix.isdigit():
            raise ValueError(f"{path.name} must start with a numeric version prefix")
        found.append((int(prefix), path))
    return sorted(found)


def connect(database: Path | str) -> sqlite3.Connection:
    """Open a configured connection.

    ``isolation_level=None`` turns off the driver's implicit transaction handling so that
    :func:`transaction` owns every BEGIN/COMMIT/ROLLBACK. WAL allows concurrent readers while
    one writer works; it does not permit two writers, which is why v0.1 admits one active job.
    """
    connection = sqlite3.connect(database, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(connection: sqlite3.Connection) -> int:
    """Apply any migrations the database has not seen. Returns the resulting version.

    Idempotent: calling it on an up-to-date database applies nothing. Each migration runs in
    its own transaction, so a failure leaves the database at the last good version rather than
    half-migrated.
    """
    current = schema_version(connection)
    for version, path in _migration_files():
        if version <= current:
            continue
        # executescript() issues an implicit COMMIT before running, so the transaction has to
        # live inside the script itself rather than around the call. SQLite DDL is
        # transactional, so a failure part way through rolls the whole migration back.
        script = f"BEGIN;\n{path.read_text()}\nPRAGMA user_version = {version};\nCOMMIT;"
        try:
            connection.executescript(script)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        current = version
    return current


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block in one explicit transaction, rolling back on any exception.

    Nesting is refused rather than silently flattened: a nested block would commit the outer
    work early, which is exactly how a half-written thesis gets persisted.
    """
    if connection.in_transaction:
        raise RuntimeError("a transaction is already open; nested transactions are not supported")
    connection.execute("BEGIN")
    try:
        yield connection
    except Exception:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")


def open_database(database: Path | str) -> sqlite3.Connection:
    """Connect and migrate in one step."""
    connection = connect(database)
    migrate(connection)
    return connection
