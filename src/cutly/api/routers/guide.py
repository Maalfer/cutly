"""Guía en Markdown para agentes, con la URL base del propio servidor."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from cutly.auth import Principal, require_read

router = APIRouter(tags=["system"])
GUIDE = Path(__file__).resolve().parents[4] / "docs" / "AGENT_GUIDE.md"


@router.get("/agent-guide", response_class=PlainTextResponse)
def agent_guide(request: Request, _: Principal = Depends(require_read)):
    """Guía de uso de la API pensada para que Claude Code (u otro agente) edite vídeos."""
    base = str(request.base_url)
    text = GUIDE.read_text() if GUIDE.is_file() else "Guía no disponible en este despliegue."
    return PlainTextResponse(
        text.replace("{{BASE_URL_NOSLASH}}", base.rstrip("/")).replace("{{BASE_URL}}", base),
        media_type="text/markdown; charset=utf-8",
    )
