import pytest
from fastapi.testclient import TestClient

from cutly.config import Settings, get_settings
from cutly.db.session import reset_engine

# Los tests nunca deben leer el .env de producción.
Settings.model_config["env_file"] = None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTLY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CUTLY_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("CUTLY_QUEUE_MODE", "inline")
    monkeypatch.setenv("CUTLY_UPLOAD_CHUNK_BYTES", "8192")
    get_settings.cache_clear()
    reset_engine()
    from cutly.api.app import create_app

    with TestClient(create_app()) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    """Vídeo de 3 s con audio, generado con ffmpeg (no se versionan binarios)."""
    import subprocess

    path = tmp_path_factory.mktemp("vid") / "sample.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )  # fmt: skip
    return path


@pytest.fixture
def writer(client):
    """Cliente autenticado con API key de escritura."""
    from sqlmodel import Session

    from cutly.auth import generate_api_key
    from cutly.db.session import get_engine

    with Session(get_engine()) as s:
        _, token = generate_api_key(s, "test", can_write=True)
    client.headers["Authorization"] = f"Bearer {token}"
    return client
