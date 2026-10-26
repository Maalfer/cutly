"""Borrado de un medio: debe eliminar filas Y archivos del disco de forma transaccional."""

from sqlmodel import Session

from cutly.config import get_settings
from cutly.db.models import Job
from cutly.db.session import get_engine

API = "/api/v1"


def test_delete_media_removes_rows_and_files(writer, sample_video):
    media_id = writer.post(
        f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()
    ).json()["media_id"]
    p = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0, "source_out": 2}).json()

    s = get_settings()
    media_dir = s.media_dir / media_id
    render_dir = s.renders_dir / p["id"]
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / "final.mp4").write_bytes(b"x" * 1024)
    # Un job asociado (p. ej. un render en cola) debe desaparecer y no bloquear el borrado.
    with Session(get_engine()) as session:
        session.add(Job(type="project.render", status="queued", params={"project_id": p["id"]}))
        session.commit()

    r = writer.delete(f"{API}/media/{media_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["projects_deleted"] == 1 and body["jobs_cancelled"] >= 1
    assert body["freed_bytes"] >= 1024

    # Nada debe quedar en disco ni en la BD.
    assert not media_dir.exists()
    assert not render_dir.exists()
    assert (
        not any(s.data_dir.joinpath(".trash").glob(f"media-{media_id}-*")) if (s.data_dir / ".trash").exists() else True
    )
    assert writer.get(f"{API}/media/{media_id}").status_code == 404
    assert writer.get(f"{API}/projects/{p['id']}").status_code == 404
    with Session(get_engine()) as session:
        assert session.get(Job, 1) is None or all(
            j.params.get("project_id") != p["id"] for j in session.query(Job).all()
        )


def test_delete_media_missing_files_is_idempotent(writer, sample_video):
    """Si los archivos ya no están, el borrado debe funcionar igual."""
    media_id = writer.post(
        f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()
    ).json()["media_id"]
    import shutil

    shutil.rmtree(get_settings().media_dir / media_id, ignore_errors=True)
    assert writer.delete(f"{API}/media/{media_id}").status_code == 200
    assert writer.delete(f"{API}/media/{media_id}").status_code == 404


def test_delete_media_restores_files_if_db_fails(writer, sample_video, monkeypatch):
    """Si el commit falla, los archivos apartados vuelven a su sitio (no se pierde nada)."""
    media_id = writer.post(
        f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()
    ).json()["media_id"]
    media_dir = get_settings().media_dir / media_id
    assert media_dir.exists()

    from sqlmodel import Session as S

    from cutly.services.ingest import media_store

    class Boom(S):
        def commit(self):
            raise RuntimeError("fallo simulado")

    with S(get_engine()) as session:
        media = session.get(__import__("cutly.db.models", fromlist=["Media"]).Media, media_id)
        session.expunge(media)
        boom = Boom(bind=session.get_bind())
        try:
            media_store.delete_media(boom, media)
        except RuntimeError:
            pass
        finally:
            boom.close()
    assert media_dir.exists()
    assert (media_dir / "original.mp4").exists()
    assert writer.get(f"{API}/media/{media_id}").status_code == 200
