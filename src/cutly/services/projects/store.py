"""Persistencia del proyecto: creación, operaciones con historial, deshacer/rehacer y concurrencia."""

import shutil
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlmodel import Session, col, delete, select

from cutly.config import get_settings
from cutly.db.models import ClipCandidate, Media, Project, ProjectHistory, Transcript
from cutly.schema.ops import OpError, apply_ops
from cutly.schema.project import CURRENT_VERSION, Output, ProjectDoc, Rect, Reframe, SubtitleLayer, TimelineClip
from cutly.schema.versioning import migrate_doc
from cutly.services.projects.hooks import check_layer

MAX_HISTORY = 200


class Conflict(Exception):
    pass


def delete_project_rows(session: Session, project_id: str, remove_files: bool = True) -> None:
    """Borra el historial y luego el proyecto, en ese orden (no hay relationship que ordene el borrado).

    `remove_files=False` deja los renderizados en disco para que el llamante los mueva/borre de forma
    transaccional (lo usa el borrado de un medio completo).
    """
    session.exec(delete(ProjectHistory).where(col(ProjectHistory.project_id) == project_id))  # type: ignore[call-overload]
    session.flush()
    session.exec(delete(Project).where(col(Project.id) == project_id))  # type: ignore[call-overload]
    session.flush()
    if remove_files:
        shutil.rmtree(get_settings().renders_dir / project_id, ignore_errors=True)  # sus MP4 renderizados


def has_transcript(session: Session, media_id: str) -> bool:
    return session.exec(select(Transcript.id).where(Transcript.media_id == media_id)).first() is not None


def create_project(
    session: Session,
    media: Media,
    name: str | None,
    candidate: ClipCandidate | None,
    source_in: float | None,
    source_out: float | None,
    subtitles: bool,
    layout: str = "vertical",
) -> Project:
    if candidate is not None:
        if candidate.media_id != media.id:
            raise OpError("El candidato pertenece a otro vídeo")
        source_in, source_out = candidate.start, candidate.end
        name = name or candidate.title
    if source_in is None or source_out is None:
        raise OpError("Indica `candidate_id` o bien `source_in` y `source_out` (segundos del vídeo original)")
    doc = ProjectDoc(media_id=media.id, timeline=[TimelineClip(source_in=source_in, source_out=source_out)])
    if media.duration and source_out > media.duration + 0.5:
        raise OpError(f"source_out={source_out:g} supera la duración del vídeo ({media.duration:g} s)")
    if layout == "horizontal":  # 16:9 a pantalla completa (YouTube): sin recorte vertical
        doc.output = Output(width=1920, height=1080, fps=doc.output.fps)
        doc.reframe = Reframe(mode="custom", game=Rect(x=0, y=0, w=1, h=1), game_fit="contain")
    if subtitles and has_transcript(session, media.id):
        doc.layers.append(SubtitleLayer(end=doc.duration))
    row = Project(
        name=name or f"Proyecto de {media.filename}",
        media_id=media.id,
        candidate_id=candidate.id if candidate else None,
        schema_version=CURRENT_VERSION,
        data=doc.model_dump(mode="json"),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def load_doc(session: Session, row: Project) -> ProjectDoc:
    data, changed = migrate_doc(row.data)
    doc = ProjectDoc.model_validate(data)
    if changed:  # migración perezosa de esquema, sin entrada de historial
        row.data, row.schema_version = doc.model_dump(mode="json"), CURRENT_VERSION
        session.add(row)
        session.commit()
    return doc


def _entries(session: Session, row: Project) -> list[ProjectHistory]:
    return list(
        session.exec(select(ProjectHistory).where(ProjectHistory.project_id == row.id).order_by(ProjectHistory.seq))
    )


def can_undo_redo(session: Session, row: Project) -> tuple[bool, bool]:
    seqs = [e.seq for e in _entries(session, row)]
    return (row.history_cursor in seqs), ((row.history_cursor + 1) in seqs)


def _write(session: Session, row: Project, new_data: dict, cursor: int, base_version: int | None) -> None:
    """Escritura condicionada a la versión: si otro cliente cambió el proyecto, falla con Conflict."""
    expected = row.version if base_version is None else base_version
    res = session.execute(
        update(Project)
        .where(col(Project.id) == row.id, col(Project.version) == expected)
        .values(data=new_data, history_cursor=cursor, version=expected + 1, updated_at=datetime.now(UTC))
    )
    if res.rowcount == 0:  # type: ignore[attr-defined]
        session.rollback()
        raise Conflict(
            f"El proyecto cambió desde la versión {expected}: léelo de nuevo "
            f"(GET /projects/{row.id}) y reaplica el cambio"
        )


def apply_batch(
    session: Session,
    row: Project,
    ops: list[Any],
    label: str | None,
    base_version: int | None,
    media_duration: float | None,
) -> ProjectDoc:
    old = load_doc(session, row)
    new = apply_ops(old, ops, media_duration, layer_hook=check_layer)
    old_d, new_d = old.model_dump(mode="json"), new.model_dump(mode="json")
    changed = {k: v for k, v in new_d.items() if old_d.get(k) != v}
    if not changed:
        return new  # sin cambios: no ensucia el historial
    seq = row.history_cursor + 1
    session.exec(delete(ProjectHistory).where(col(ProjectHistory.project_id) == row.id, col(ProjectHistory.seq) >= seq))  # type: ignore[call-overload]
    session.add(
        ProjectHistory(
            project_id=row.id, seq=seq, op=(label or ", ".join(o.op for o in ops))[:200],
            forward=[{"set": changed}], inverse=[{"set": {k: old_d[k] for k in changed}}],
        )
    )  # fmt: skip
    _write(session, row, new_d, seq, base_version)
    session.exec(
        delete(ProjectHistory).where(
            col(ProjectHistory.project_id) == row.id, col(ProjectHistory.seq) <= seq - MAX_HISTORY
        )
    )  # type: ignore[call-overload]
    session.commit()
    session.refresh(row)
    return new


def _step(session: Session, row: Project, direction: str, base_version: int | None) -> ProjectDoc:
    seq = row.history_cursor if direction == "undo" else row.history_cursor + 1
    entry = session.exec(
        select(ProjectHistory).where(ProjectHistory.project_id == row.id, ProjectHistory.seq == seq)
    ).first()
    if entry is None:
        raise OpError("No hay nada que deshacer" if direction == "undo" else "No hay nada que rehacer")
    patch = (entry.inverse if direction == "undo" else entry.forward)[0]["set"]
    new_data = {**row.data, **patch}
    ProjectDoc.model_validate(new_data)
    _write(session, row, new_data, seq - 1 if direction == "undo" else seq, base_version)
    session.commit()
    session.refresh(row)
    return ProjectDoc.model_validate(row.data)


def undo(session: Session, row: Project, base_version: int | None = None) -> ProjectDoc:
    return _step(session, row, "undo", base_version)


def redo(session: Session, row: Project, base_version: int | None = None) -> ProjectDoc:
    return _step(session, row, "redo", base_version)


def history(session: Session, row: Project) -> list[dict]:
    return [
        {"seq": e.seq, "label": e.op, "created_at": e.created_at, "applied": e.seq <= row.history_cursor}
        for e in _entries(session, row)
    ]
