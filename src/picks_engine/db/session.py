"""Engine creation, schema setup and dialect-aware upserts."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from .schema import HYPERTABLES, metadata

log = logging.getLogger(__name__)


def get_engine(url: str) -> Engine:
    kwargs = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = sa.create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":

        @sa.event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - trivial
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def init_db(engine: Engine) -> None:
    """Create every table, and on Postgres turn the snapshot tables into hypertables."""
    metadata.create_all(engine)
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        try:
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        except sa.exc.DBAPIError:
            log.warning("TimescaleDB is not available; snapshot tables stay plain Postgres tables.")
            return
    for table, column in HYPERTABLES.items():
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "SELECT create_hypertable(:t, :c, if_not_exists => TRUE, migrate_data => TRUE)"
                ),
                {"t": table, "c": column},
            )


def _insert_for(conn: Connection, table: sa.Table):
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif conn.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise NotImplementedError(f"upsert not supported on {conn.dialect.name}")
    return insert(table)


def upsert(
    conn: Connection,
    table: sa.Table,
    rows: Iterable[dict],
    key: Sequence[str],
    update: Sequence[str] | None = None,
) -> int:
    """Insert rows, updating `update` columns (default: all non-key columns) on key conflict.

    Pass update=[] to ignore conflicts instead.
    """
    rows = list(rows)
    if not rows:
        return 0
    stmt = _insert_for(conn, table)
    if update is None:
        update = [c for c in rows[0] if c not in key]
    if update:
        stmt = stmt.on_conflict_do_update(
            index_elements=list(key), set_={c: stmt.excluded[c] for c in update}
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=list(key))
    # Chunk to stay under driver parameter limits.
    cols = max(len(rows[0]), 1)
    chunk = max(1, 30000 // cols)
    for i in range(0, len(rows), chunk):
        conn.execute(stmt, rows[i : i + chunk])
    return len(rows)
