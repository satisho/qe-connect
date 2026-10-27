"""Database engine, sessions and start-up migrations."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

log = logging.getLogger("qe_connect.db")


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kw: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
    eng = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _rec):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return eng


engine: Engine = None  # type: ignore[assignment]
SessionLocal: sessionmaker = None  # type: ignore[assignment]


def init_engine(url: str | None = None) -> Engine:
    global engine, SessionLocal
    url = url or settings.db_url
    if url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def run_migrations(url: str | None = None) -> None:
    """Bring the database up to the latest schema. Runs at every start-up."""
    from alembic import command
    from alembic.script import ScriptDirectory

    url = url or settings.db_url
    cfg = alembic_config(url)
    known = {s.revision for s in ScriptDirectory.from_config(cfg).walk_revisions()}
    with engine.connect() as conn:
        if inspect(conn).has_table("alembic_version"):
            current = {r[0] for r in conn.exec_driver_sql("SELECT version_num FROM alembic_version")}
            unknown = current - known
            if unknown:
                raise SystemExit(
                    "The database was created by a newer or unreleased version of QE Connect "
                    f"(schema revision {', '.join(sorted(unknown))}). Restore a backup of the data folder, "
                    "or run a QE Connect version that knows this revision."
                )
    command.upgrade(cfg, "head")
    log.info("Database schema is up to date")
