"""Aplicación FastAPI. Todo bajo /api/v1."""

import hashlib
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from cutly.api.routers import (
    analysis,
    assets,
    auth,
    candidates,
    effects,
    guide,
    jobs,
    media,
    presets,
    projects,
    render,
    scenes,
    transcripts,
    uploads,
    verify,
)
from cutly.auth import Principal, require_read
from cutly.config import get_settings
from cutly.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Limpieza de restos de borrados interrumpidos y huérfanos (idempotente, nunca toca subidas en curso).
    try:
        from cutly.services.ingest.media_store import purge_orphans

        purge_orphans()
    except Exception:  # noqa: BLE001 - el arranque no debe fallar por la limpieza
        pass
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Cutly API",
        version="0.1.0",
        description="Editor de vídeo API-first. La web y Claude (MCP) usan estos mismos endpoints.",
        lifespan=lifespan,
        # Documentación y esquema deshabilitados por defecto: se exponen más abajo detrás de autenticación
        # (sin esto, cualquiera sin sesión ni API key podía ver el mapa completo de la API).
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    hits: dict[str, deque] = defaultdict(deque)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        # Límite básico por IP/ventana de 60 s; el de Nginx es la primera barrera.
        if _CHUNK_PATH.match(request.url.path):  # los trozos de subida son muchos y legítimos: no cuentan
            return await call_next(request)
        ip = request.client.host if request.client else "?"
        q = hits[ip]
        t = time.monotonic()
        while q and t - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_minute:
            return JSONResponse({"detail": "Demasiadas peticiones, espera un minuto"}, 429)
        q.append(t)
        return await call_next(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=settings.env == "prod",
        same_site="lax",
        max_age=60 * 60 * 24 * 14,
    )

    @app.get("/api/v1/health", tags=["system"])
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def openapi_spec(_: Principal = Depends(require_read)):
        return JSONResponse(app.openapi())

    @app.get("/api/v1/docs", include_in_schema=False)
    def swagger_docs(_: Principal = Depends(require_read)):
        return get_swagger_ui_html(openapi_url="/api/v1/openapi.json", title=f"{app.title} - Docs")

    @app.get("/redoc", include_in_schema=False)
    def redoc_docs(_: Principal = Depends(require_read)):
        return get_redoc_html(openapi_url="/api/v1/openapi.json", title=f"{app.title} - ReDoc")

    for r in (
        auth,
        guide,
        assets,
        presets,
        effects,
        uploads,
        media,
        transcripts,
        analysis,
        candidates,
        projects,
        render,
        scenes,
        verify,
        jobs,
    ):
        app.include_router(r.router, prefix="/api/v1")
    web = settings.web_dir or Path(__file__).resolve().parents[3] / "web"
    csp = _build_csp(web / "index.html")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if not request.url.path.startswith("/api/") or request.url.path.endswith("/docs"):
            resp.headers.setdefault("Content-Security-Policy", csp)
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        elif not request.url.path.startswith("/vendor/"):
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp

    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


_CHUNK_PATH = re.compile(r"^/api/v1/uploads/[^/]+/chunks/\d+$")


def _build_csp(index: Path) -> str:
    """CSP estricta: solo recursos propios; el import map inline se autoriza por su hash."""
    hashes = ""
    if index.is_file():
        for m in re.finditer(r"<script[^>]*>(.*?)</script>", index.read_text(), re.S):
            if m.group(1).strip():
                digest = hashlib.sha256(m.group(1).encode()).digest()
                hashes += " 'sha256-" + __import__("base64").b64encode(digest).decode() + "'"
    return (
        f"default-src 'self'; script-src 'self'{hashes}; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )


app = create_app()
