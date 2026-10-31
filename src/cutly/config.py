"""Configuración por variables de entorno (prefijo CUTLY_)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CUTLY_", env_file=".env", extra="ignore")

    # Por defecto "prod": si se olvida configurar CUTLY_ENV en un despliegue real, la cookie de sesión
    # sigue llevando el atributo Secure en vez de quedarse en texto claro sobre HTTP sin que nadie lo note.
    # El desarrollo local declara CUTLY_ENV=dev explícitamente (ver tests/conftest.py).
    env: str = "prod"
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/cutly.db"
    redis_url: str = "redis://localhost:6379/0"
    session_secret: str = "cambia-esto"
    max_upload_bytes: int = 40 * 1024**3
    upload_chunk_bytes: int = 8 * 1024**2
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute: str = "int8"
    whisper_threads: int = 0  # 0 = automático
    whisper_beam_size: int = 1  # 1 = voraz (rápido en CPU); 5 en GPU
    whisper_window_s: int = 600  # ventana de audio en memoria (~38 MB por 10 min)
    # faster_whisper | remote | fake (fake solo para tests)
    transcriber_backend: str = "faster_whisper"
    transcriber_remote_url: str = ""
    video_encoder: str = "libx264"
    retention_originals_days: int = 0
    retention_proxies_days: int = 0
    rate_limit_per_minute: int = 120
    web_dir: Path | None = None  # por defecto, <repo>/web
    assets_dir: Path | None = None  # por defecto, <repo>/assets
    # "rq" (Redis, producción) o "inline" (síncrono, tests y desarrollo sin Redis)
    queue_mode: str = "rq"
    simple_upload_max_bytes: int = 100 * 1024**2
    ffmpeg_nice: int = 10  # prioridad baja para no ahogar el resto del servidor
    ffmpeg_threads: int = 0  # 0 = automático
    job_timeout_s: int = 6 * 3600

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def builtin_assets_dir(self) -> Path:
        return self.assets_dir or Path(__file__).resolve().parents[2] / "assets"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "prod" and s.session_secret == "cambia-esto":
        raise RuntimeError(
            "CUTLY_SESSION_SECRET no está configurado (sigue en el valor de ejemplo del código). "
            "En producción esto permite forjar cookies de sesión de cualquier usuario: "
            "define CUTLY_SESSION_SECRET con un valor aleatorio, o CUTLY_ENV=dev si es un entorno local."
        )
    return s
