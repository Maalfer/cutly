import sqlite3

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlmodel import SQLModel

from cutly.config import get_settings
from cutly.db.session import get_engine, reset_engine, run_migrations


def _env(tmp_path, monkeypatch, name="m.db"):
    monkeypatch.setenv("CUTLY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CUTLY_DATABASE_URL", f"sqlite:///{tmp_path}/{name}")
    get_settings.cache_clear()
    reset_engine()


def test_fresh_db_matches_models(tmp_path, monkeypatch):
    """Las migraciones deben producir exactamente el esquema de los modelos (sin diferencias)."""
    _env(tmp_path, monkeypatch)
    run_migrations()
    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), SQLModel.metadata)
    assert diff == [], f"Falta una migración: {diff}"


def test_legacy_db_is_stamped_and_upgraded(tmp_path, monkeypatch):
    """Una BD creada antes de Alembic (sin columnas nuevas) se actualiza conservando sus filas."""
    _env(tmp_path, monkeypatch, "legacy.db")
    run_migrations()
    path = tmp_path / "legacy.db"
    reset_engine()
    con = sqlite3.connect(path)
    con.execute("DROP TABLE alembic_version")
    con.execute("ALTER TABLE project RENAME TO project_new")
    con.execute("CREATE TABLE project (id VARCHAR PRIMARY KEY, name VARCHAR, media_id VARCHAR, schema_version INT, "
                "data JSON, history_cursor INT, updated_at DATETIME)")  # fmt: skip
    con.execute("INSERT INTO media (id, filename, original_path, size_bytes, status, metadata_json, created_at) "
                "VALUES ('m_1','a.mp4','/x',0,'ready','{}','2026-01-01')")  # fmt: skip
    con.execute("INSERT INTO project VALUES ('p_1','viejo','m_1',1,'{}',0,'2026-01-01')")
    con.execute("DROP TABLE project_new")
    con.execute("ALTER TABLE preset DROP COLUMN description")  # el esquema anterior no la tenía
    con.commit()
    con.close()
    run_migrations()
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(project)")}
    assert {"version", "candidate_id"} <= cols
    assert "description" in {r[1] for r in con.execute("PRAGMA table_info(preset)")}
    assert con.execute("SELECT name, version FROM project").fetchone() == ("viejo", 1)
    con.close()
