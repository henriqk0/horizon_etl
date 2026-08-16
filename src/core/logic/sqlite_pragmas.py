"""
SQLite performance pragmas for the domain database engines.

The domain SQLAlchemy clients (eo_lib and research_domain PostgresClient)
default to a SQLite file (db/horizon.db) with the slow defaults:
journal_mode=delete and synchronous=FULL.  With these defaults every
COMMIT performs a journal write plus ~2 fsyncs, which serializes flows
that write per-record data (e.g. Lattes advisorships) to less than one
record per second.

Attaching a "connect" listener that flips journal_mode to WAL and
synchronous to NORMAL mirrors what the tracking engine already does in
src/tracking/service_factory.py, removing the per-commit fsync cost
without changing transaction semantics.

Register once at startup via configure_application_sqlite_engines().
"""

import threading

from loguru import logger

_lock = threading.Lock()
_configured_engines: set[int] = set()


def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def _attach_sqlite_pragmas(engine) -> bool:
    if "sqlite" not in str(getattr(engine, "url", "")):
        return False
    from sqlalchemy import event

    event.listen(engine, "connect", _configure_sqlite_connection)
    return True


def configure_application_sqlite_engines() -> None:
    """Configure and attach SQLite pragmas to the domain engines, idempotently."""
    from eo_lib.infrastructure.database.postgres_client import (
        PostgresClient as EoLibPostgresClient,
    )
    from research_domain.infrastructure.database.postgres_client import (
        PostgresClient as ResearchPostgresClient,
    )

    for client_class in (ResearchPostgresClient, EoLibPostgresClient):
        with _lock:
            client = client_class()
            engine = getattr(client, "_engine", None)
            if engine is None or id(engine) in _configured_engines:
                continue
            if _attach_sqlite_pragmas(engine):
                _configured_engines.add(id(engine))
                logger.debug(
                    "Configured SQLite WAL/synchronous pragmas on engine {}", engine.url
                )
