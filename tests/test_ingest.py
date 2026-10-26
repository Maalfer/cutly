import hashlib
import sys
import time
from pathlib import Path

import pytest

from cutly.services.sanitize.paths import UnsafePath, ensure_within, safe_filename
from cutly.worker.jobs import JobContext
from cutly.worker.subprocess_runner import JobCancelled, ProcessError, run_ffmpeg

API = "/api/v1"


def upload(c, path: Path, skip: set[int] = frozenset()):
    data = path.read_bytes()
    up = c.post(f"{API}/uploads", json={"filename": path.name, "size": len(data)}).json()
    cs = up["chunk_size"]
    for n in range(up["total_chunks"]):
        if n in skip:
            continue
        part = data[n * cs : (n + 1) * cs]
        r = c.put(f"{API}/uploads/{up['upload_id']}/chunks/{n}", content=part,
                  headers={"X-Chunk-SHA256": hashlib.sha256(part).hexdigest()})  # fmt: skip
        assert r.status_code == 200, r.text
    return up, data


def test_chunked_upload_resume_and_process(writer, sample_video):
    up, data = upload(writer, sample_video, skip={1})
    assert up["total_chunks"] >= 3
    uid = up["upload_id"]
    # incompleto → 409 con los que faltan
    r = writer.post(f"{API}/uploads/{uid}/complete")
    assert r.status_code == 409 and "[1]" in r.json()["detail"]
    # reanudar: el estado dice qué falta
    assert 1 not in writer.get(f"{API}/uploads/{uid}").json()["received"]
    cs = up["chunk_size"]
    assert writer.put(f"{API}/uploads/{uid}/chunks/1", content=data[cs : 2 * cs]).status_code == 200

    r = writer.post(f"{API}/uploads/{uid}/complete")
    assert r.status_code == 200, r.text
    media_id = r.json()["media_id"]
    # idempotente
    assert writer.post(f"{API}/uploads/{uid}/complete").json()["media_id"] == media_id

    m = writer.get(f"{API}/media/{media_id}").json()
    assert m["status"] == "ready" and m["has_proxy"] and m["has_peaks"]
    assert abs(m["duration"] - 3.0) < 0.2 and m["metadata"]["height"] == 360
    assert all(writer.get(f"{API}/jobs/{j}").json()["status"] == "done" for j in r.json()["jobs"])

    peaks = writer.get(f"{API}/media/{media_id}/peaks", params={"bins": 10}).json()
    assert peaks["count"] == 10 and max(peaks["max"]) >= 12 and min(peaks["min"]) <= -12  # el seno de 440 Hz se ve
    assert writer.get(f"{API}/media/{media_id}/proxy.mp4").status_code == 200

    assert writer.delete(f"{API}/media/{media_id}").status_code == 200
    assert writer.get(f"{API}/media/{media_id}").status_code == 404


def test_bad_chunk_hash_and_size_rejected(writer, sample_video):
    data = sample_video.read_bytes()
    up = writer.post(f"{API}/uploads", json={"filename": "a.mp4", "size": len(data)}).json()
    url = f"{API}/uploads/{up['upload_id']}/chunks/0"
    part = data[: up["chunk_size"]]
    assert writer.put(url, content=part, headers={"X-Chunk-SHA256": "0" * 64}).status_code == 422
    assert writer.put(url, content=part[:-1]).status_code == 400
    assert writer.put(url, content=part + b"x").status_code == 413
    assert writer.put(f"{API}/uploads/{up['upload_id']}/chunks/999", content=b"").status_code == 422


def test_non_video_rejected(writer, tmp_path):
    f = tmp_path / "fake.mp4"
    f.write_bytes(b"esto no es un video" * 5000)
    up, _ = upload(writer, f)
    r = writer.post(f"{API}/uploads/{up['upload_id']}/complete")
    assert r.status_code == 422


def test_simple_upload_and_limits(writer, sample_video):
    r = writer.post(f"{API}/media/simple", params={"filename": "s.mp4"}, content=sample_video.read_bytes())
    assert r.status_code == 200 and writer.get(f"{API}/media").json()[0]["status"] == "ready"
    assert writer.post(f"{API}/media/simple", params={"filename": "x.exe"}, content=b"x").status_code == 422


def test_read_only_key_cannot_upload(client):
    from sqlmodel import Session

    from cutly.auth import generate_api_key
    from cutly.db.session import get_engine

    with Session(get_engine()) as s:
        _, token = generate_api_key(s, "ro", can_write=False)
    r = client.post(f"{API}/uploads", json={"filename": "a.mp4", "size": 10},
                    headers={"Authorization": f"Bearer {token}"})  # fmt: skip
    assert r.status_code == 403


@pytest.mark.parametrize("bad", ["../../etc/passwd.mp4", "..\\x.mp4", "a;rm -rf.mp4", ".mp4"])
def test_safe_filename_strips_paths(bad):
    try:
        out = safe_filename(bad)
    except UnsafePath:
        return
    assert "/" not in out and "\\" not in out and ";" not in out and not out.startswith(".")


def test_ensure_within(tmp_path):
    with pytest.raises(UnsafePath):
        ensure_within(tmp_path, tmp_path / ".." / "x")


def test_runner_timeout_and_cancel(tmp_path):
    # Falso "ffmpeg": un proceso que duerme, para probar el control sin vídeo.
    cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
    t = time.monotonic()
    with pytest.raises(ProcessError, match="timeout"):
        run_ffmpeg(cmd, duration=None, timeout=1, cancelled=lambda: False)
    assert time.monotonic() - t < 10
    with pytest.raises(JobCancelled):
        run_ffmpeg(cmd, duration=None, timeout=60, cancelled=lambda: True)


def test_job_cancel_endpoint(writer):
    from sqlmodel import Session

    from cutly.db.models import Job
    from cutly.db.session import get_engine

    with Session(get_engine()) as s:
        job = Job(type="media.proxy", params={"media_id": "x"})
        s.add(job)
        s.commit()
        jid = job.id
    r = writer.post(f"{API}/jobs/{jid}/cancel")
    assert r.json().get("status") == "cancelled", (r.status_code, r.text)
    from cutly.worker.jobs import run_job

    run_job(jid)  # un job cancelado no se ejecuta
    assert writer.get(f"{API}/jobs/{jid}").json()["status"] == "cancelled"
    assert JobContext(jid, {}).cancelled() is True


def test_client_chosen_chunk_size(writer, sample_video):
    data = sample_video.read_bytes()
    up = writer.post(f"{API}/uploads", json={"filename": "v.mp4", "size": len(data), "chunk_size": 262144}).json()
    assert up["chunk_size"] == 262144 and up["total_chunks"] == -(-len(data) // 262144)
    assert writer.post(f"{API}/uploads", json={"filename": "v.mp4", "size": 10, "chunk_size": 1000}).status_code == 422
    assert writer.post(f"{API}/uploads", json={"filename": "v.mp4", "size": 10, "chunk_size": 10**9}).status_code == 422


def test_chunk_uploads_are_exempt_from_rate_limit(tmp_path, monkeypatch):
    """Miles de trozos legítimos no deben disparar el límite de peticiones (429)."""
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from cutly.api.app import create_app
    from cutly.auth import generate_api_key
    from cutly.config import get_settings
    from cutly.db.session import get_engine, reset_engine

    monkeypatch.setenv("CUTLY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CUTLY_DATABASE_URL", f"sqlite:///{tmp_path}/r.db")
    monkeypatch.setenv("CUTLY_RATE_LIMIT_PER_MINUTE", "5")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(create_app()) as c:
        with Session(get_engine()) as s:
            _, tok = generate_api_key(s, "k", can_write=True)
        h = {"Authorization": f"Bearer {tok}"}
        up = c.post(
            f"{API}/uploads", json={"filename": "v.mp4", "size": 262144, "chunk_size": 262144}, headers=h
        ).json()
        url = f"{API}/uploads/{up['upload_id']}/chunks/0"
        assert {c.put(url, content=b"x" * 262144, headers=h).status_code for _ in range(15)} == {200}
        assert 429 in {c.get(f"{API}/auth/me", headers=h).status_code for _ in range(15)}  # el resto sí se limita
    reset_engine()
