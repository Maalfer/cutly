"""Modelo de datos. Los JSON del proyecto son la fuente de verdad de la edición."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("u"), primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=now)


class ApiKey(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("k"), primary_key=True)
    name: str
    key_hash: str = Field(unique=True, index=True)  # sha256 del token (alta entropía)
    prefix: str  # primeros caracteres, para identificarla en listados
    can_write: bool = False
    created_at: datetime = Field(default_factory=now)
    last_used_at: datetime | None = None
    revoked: bool = False


class Media(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("m"), primary_key=True)
    filename: str
    original_path: str
    proxy_path: str | None = None
    peaks_path: str | None = None
    duration: float | None = None
    size_bytes: int = 0
    status: str = "ready"
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Transcript(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("t"), primary_key=True)
    media_id: str = Field(foreign_key="media.id", index=True)
    language: str = "es"
    # segmentos: [{id,start,end,text,words:[{w,start,end,p}]}]
    segments: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Project(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("p"), primary_key=True)
    name: str
    media_id: str = Field(foreign_key="media.id", index=True)
    schema_version: int = 1
    candidate_id: str | None = None  # candidato del que nació el proyecto
    version: int = 1  # control de concurrencia optimista: sube en cada cambio
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    history_cursor: int = 0
    updated_at: datetime = Field(default_factory=now)


class ProjectHistory(SQLModel, table=True):
    """Parches JSON por operación, para deshacer/rehacer."""

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    seq: int = Field(index=True)
    op: str
    forward: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    inverse: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class ClipCandidate(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("cc"), primary_key=True)
    media_id: str = Field(foreign_key="media.id", index=True)
    start: float
    end: float
    score: float = 0.0
    title: str = ""
    reason: str = ""
    criteria: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "proposed"  # proposed | accepted | discarded


class Asset(SQLModel, table=True):
    id: str = Field(primary_key=True)  # p. ej. "icons/arrow-right"
    kind: str  # icon | font | overlay
    path: str
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    description: str = ""
    license: str = ""


class Preset(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("pr"), primary_key=True)
    kind: str  # subtitle | text | animation | color | transition | layer
    name: str = Field(index=True)
    description: str = ""
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("j"), primary_key=True)
    type: str
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    params: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Upload(SQLModel, table=True):
    """Subida por trozos reanudable. El archivo se escribe en su sitio (pwrite) sin duplicar disco."""

    id: str = Field(default_factory=lambda: new_id("up"), primary_key=True)
    filename: str
    size: int
    chunk_size: int
    total_chunks: int
    path: str
    status: str = "uploading"  # uploading | complete
    media_id: str | None = None
    created_at: datetime = Field(default_factory=now)


class UploadChunk(SQLModel, table=True):
    upload_id: str = Field(foreign_key="upload.id", primary_key=True)
    n: int = Field(primary_key=True)
