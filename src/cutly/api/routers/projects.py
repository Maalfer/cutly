"""Proyectos de edición: CRUD, operaciones atómicas por lotes, deshacer/rehacer y layers."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.db.models import ClipCandidate, Media, Project, now
from cutly.db.session import get_session
from cutly.schema.ops import AddLayer, Op, OpError, RemoveLayer, UpdateLayer, fmt_validation
from cutly.schema.project import Layer, ProjectDoc
from cutly.services.projects import store
from cutly.services.projects.check import check_project

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    media_id: str
    name: str | None = Field(None, max_length=120)
    candidate_id: str | None = Field(
        None, description="Crea el proyecto con el rango de un candidato aceptado/propuesto"
    )
    source_in: float | None = Field(None, ge=0, description="Inicio (s del original) si no hay candidato")
    source_out: float | None = Field(None, gt=0)
    subtitles: bool = Field(True, description="Añade una layer de subtítulos desde la transcripción si existe")


class OpsIn(BaseModel):
    ops: list[Op] = Field(min_length=1, max_length=100, description="Se aplican en orden, todo o nada")
    label: str | None = Field(None, max_length=200, description="Nombre del paso en el historial")
    base_version: int | None = Field(None, description="Si se indica y no coincide con la actual: 409")


class StepIn(BaseModel):
    base_version: int | None = None


class LayerIn(BaseModel):
    layer: Layer
    base_version: int | None = None


class LayerPatchIn(BaseModel):
    patch: dict[str, Any]
    base_version: int | None = None


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _row(session: Session, project_id: str) -> Project:
    row = session.get(Project, project_id)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado; lista los existentes con GET /projects")
    return row


def _media(session: Session, media_id: str) -> Media:
    m = session.get(Media, media_id)
    if m is None:
        raise HTTPException(404, "Medio no encontrado")
    return m


def _view(session: Session, row: Project, doc: ProjectDoc | None = None) -> dict:
    doc = doc or store.load_doc(session, row)
    undo, redo = store.can_undo_redo(session, row)
    return {
        "id": row.id, "name": row.name, "media_id": row.media_id, "candidate_id": row.candidate_id,
        "version": row.version, "schema_version": row.schema_version, "duration": doc.duration,
        "can_undo": undo, "can_redo": redo, "updated_at": row.updated_at,
        "warnings": check_project(doc, store.has_transcript(session, row.media_id)),
        "project": doc.model_dump(mode="json"),
    }  # fmt: skip


def _run(session: Session, row: Project, fn) -> dict:
    try:
        doc = fn()
    except OpError as e:
        raise HTTPException(422, str(e)) from e
    except ValidationError as e:
        raise HTTPException(422, fmt_validation(e)) from e
    except store.Conflict as e:
        raise HTTPException(409, str(e)) from e
    return _view(session, row, doc)


@router.get("/project-schema")
def project_schema(_: Principal = Depends(require_read)):
    """JSON Schema del documento de proyecto (tipos de layer, estilos, animaciones, límites)."""
    return ProjectDoc.model_json_schema()


@router.post("/projects")
def create_project(body: ProjectCreate, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    """Crea un proyecto de edición a partir de un candidato o de un rango del vídeo original."""
    media = _media(session, body.media_id)
    cand = None
    if body.candidate_id:
        cand = session.get(ClipCandidate, body.candidate_id)
        if cand is None:
            raise HTTPException(404, "Candidato no encontrado")
    try:
        row = store.create_project(session, media, body.name, cand, body.source_in, body.source_out, body.subtitles)
    except (OpError, ValidationError) as e:
        raise HTTPException(422, fmt_validation(e) if isinstance(e, ValidationError) else str(e)) from e
    return _view(session, row)


@router.get("/projects")
def list_projects(
    media_id: str | None = None, _: Principal = Depends(require_read), session: Session = Depends(get_session)
):
    q = select(Project).order_by(Project.updated_at.desc())  # type: ignore[attr-defined]
    if media_id:
        q = q.where(Project.media_id == media_id)
    out = []
    for r in session.exec(q).all():
        doc = store.load_doc(session, r)
        out.append({"id": r.id, "name": r.name, "media_id": r.media_id, "version": r.version,
                    "duration": doc.duration, "clips": len(doc.timeline), "layers": len(doc.layers),
                    "updated_at": r.updated_at})  # fmt: skip
    return out


@router.get("/projects/{project_id}")
def get_project(project_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    return _view(session, _row(session, project_id))


@router.patch("/projects/{project_id}")
def rename_project(
    project_id: str, body: RenameIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    row = _row(session, project_id)
    row.name, row.updated_at = body.name, now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _view(session, row)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    row = _row(session, project_id)
    store.delete_project_rows(session, row.id)
    session.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/ops")
def apply_operations(
    project_id: str, body: OpsIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """Aplica un lote de operaciones de forma atómica (todo o nada) como un único paso de historial.

    Operaciones: add_clip, split_clip, delete_clip, move_clip, set_clip_range, set_clip_speed,
    add_layer, update_layer, remove_layer, set_reframe, set_audio, set_color, set_output.
    """
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    return _run(
        session, row, lambda: store.apply_batch(session, row, body.ops, body.label, body.base_version, media.duration)
    )


@router.post("/projects/{project_id}/undo")
def undo(
    project_id: str,
    body: StepIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    row = _row(session, project_id)
    return _run(session, row, lambda: store.undo(session, row, body.base_version if body else None))


@router.post("/projects/{project_id}/redo")
def redo(
    project_id: str,
    body: StepIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    row = _row(session, project_id)
    return _run(session, row, lambda: store.redo(session, row, body.base_version if body else None))


@router.get("/projects/{project_id}/history")
def project_history(project_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    row = _row(session, project_id)
    return {"cursor": row.history_cursor, "entries": store.history(session, row)}


# Atajos para layers (equivalen a una operación suelta; son lo que usarán add_layer/update_layer/remove_layer de MCP)


@router.post("/projects/{project_id}/layers")
def add_layer(
    project_id: str, body: LayerIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    ops = [AddLayer(op="add_layer", layer=body.layer)]
    return _run(
        session,
        row,
        lambda: store.apply_batch(
            session, row, ops, f"añadir layer {body.layer.type}", body.base_version, media.duration
        ),
    )


@router.patch("/projects/{project_id}/layers/{layer_id}")
def update_layer(
    project_id: str,
    layer_id: str,
    body: LayerPatchIn,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    ops = [UpdateLayer(op="update_layer", layer_id=layer_id, patch=body.patch)]
    return _run(
        session,
        row,
        lambda: store.apply_batch(session, row, ops, f"editar layer {layer_id}", body.base_version, media.duration),
    )


@router.delete("/projects/{project_id}/layers/{layer_id}")
def remove_layer(
    project_id: str, layer_id: str, base_version: int | None = Query(None), _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):  # fmt: skip
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    ops = [RemoveLayer(op="remove_layer", layer_id=layer_id)]
    return _run(
        session,
        row,
        lambda: store.apply_batch(session, row, ops, f"borrar layer {layer_id}", base_version, media.duration),
    )
