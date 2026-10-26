"""Biblioteca de assets: iconos, fuentes, imágenes y overlays (incluidos y subidos)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlmodel import Session

from cutly.auth import Principal, require_read, require_write
from cutly.db.session import get_session
from cutly.services.assets import library as lib

router = APIRouter(tags=["assets"])


def _get(session: Session, asset_id: str) -> dict:
    a = lib.find(session, asset_id)
    if a is None:
        import difflib

        near = difflib.get_close_matches(asset_id, [x["id"] for x in lib.all_assets(session)], n=4, cutoff=0.4)
        raise HTTPException(
            404,
            f"El asset '{asset_id}' no existe." + (f" ¿Quizá {', '.join(near)}?" if near else " Lista: GET /assets"),
        )
    return a


@router.get("/assets")
def list_assets(
    kind: str | None = Query(None, description="icon | font | image | overlay"),
    tag: str | None = Query(
        None, description="Etiqueta (también por coincidencia parcial), p. ej. flecha, seguridad, emoji"
    ),
    q: str | None = Query(None, description="Búsqueda libre sobre id, etiquetas y descripción"),
    limit: int = Query(200, ge=1, le=500),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Assets disponibles. El `id` (p. ej. `icons/arrow-right`) es lo que va en `asset` de una capa icon/image; para las
    fuentes, usa su `family` en `style.font`."""
    items = lib.search(lib.all_assets(session), kind, tag, q)
    return {"count": len(items), "assets": items[:limit]}


@router.get("/assets-sheet.png")
def assets_sheet(
    kind: str | None = "icon",
    tag: str | None = None,
    q: str | None = None,
    cols: int = Query(6, ge=1, le=12),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Hoja de contacto (PNG) con los assets y su id: la forma de *ver* qué iconos hay antes de elegir uno."""
    items = lib.search(lib.all_assets(session), kind, tag, q)[:120]
    if not items:
        raise HTTPException(404, "No hay assets con ese filtro")
    return Response(lib.contact_sheet(items, cols), media_type="image/png")


@router.get("/assets/item/{asset_id:path}")
def get_asset(asset_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    return _get(session, asset_id)


@router.get("/assets/preview/{asset_id:path}")
def asset_preview(
    asset_id: str,
    size: int = Query(256, ge=32, le=1024),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    return Response(lib.preview_png(_get(session, asset_id), size), media_type="image/png")


@router.get("/assets/file/{asset_id:path}")
def asset_file(asset_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    a = _get(session, asset_id)
    p = lib.file_of(a)
    media = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(
        p.suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        p,
        media_type=media,
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/assets")
async def upload_asset(
    request: Request,
    name: str = Query(description="Nombre (minúsculas, números, - y _). El id será <carpeta>/<name>"),
    kind: str = Query(description="icon (SVG) | image (PNG/JPEG/WebP) | overlay (SVG/PNG) | font (TTF/OTF)"),
    tags: str = Query("", description="Etiquetas separadas por comas"),
    description: str = Query("", max_length=300),
    license: str = Query("", max_length=80, description="Licencia del archivo (obligatorio saber de dónde sale)"),
    replace: bool = False,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Sube un asset (cuerpo = bytes crudos del archivo). Los SVG se sanean (sin scripts ni referencias externas), las
    imágenes se validan y las fuentes se comprueban antes de guardarlas."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > 6_000_000:
            raise HTTPException(413, "Archivo demasiado grande (máx. 5 MB)")
    try:
        return lib.save_user_asset(session, name, kind, bytes(data), tags.split(","), description, license, replace)
    except lib.AssetError as e:
        raise HTTPException(409 if "ya existe" in str(e) or "incluido" in str(e) else 422, str(e)) from e


@router.delete("/assets/item/{asset_id:path}")
def delete_asset(asset_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    try:
        lib.delete_user_asset(session, asset_id)
    except lib.AssetError as e:
        raise HTTPException(403, str(e)) from e
    except LookupError as e:
        raise HTTPException(404, f"El asset '{asset_id}' no existe") from e
    return {"ok": True}
