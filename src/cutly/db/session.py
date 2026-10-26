"""Motor SQLAlchemy. SQLite en modo WAL; migrable a Postgres cambiando database_url."""

from collections.abc import Iterator

from sqlalchemy import event
from sqlmodel import Session, create_engine

from cutly.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _pragmas(dbapi_conn, _):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()

    return _engine


def reset_engine() -> None:
    """Solo para tests: descarta el motor cacheado."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def run_migrations() -> None:
    """Lleva la BD a la última versión. Una BD creada antes de Alembic (con `create_all`)
    se marca primero como baseline (0001) para no recrear sus tablas."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    tables = set(inspect(get_engine()).get_table_names())
    if "alembic_version" not in tables and "media" in tables:
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")


def init_db() -> None:
    from cutly.db import models  # noqa: F401  (registra tablas)

    settings = get_settings()
    for d in (settings.data_dir, settings.media_dir, settings.uploads_dir, settings.renders_dir):
        d.mkdir(parents=True, exist_ok=True)
    run_migrations()


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
