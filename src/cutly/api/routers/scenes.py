"""Escenas animadas (capa `scene`): catálogo de plantillas, esquema y vista previa sin crear un proyecto."""

import io
import json
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, ValidationError

from cutly.auth import Principal, require_read, require_write
from cutly.schema.scene import Scene
from cutly.services.scene import templates as TP
from cutly.services.scene.engine import Player

router = APIRouter(tags=["scenes"])
_busy = threading.Lock()  # una vista previa a la vez: el VPS es modesto
MAX_TIMES = 12

# El mismo harness que web/editor/scene-live.js (deben mantenerse en sync): controla el reloj del documento vía
# postMessage en vez del reloj real, para que el editor pueda sincronizarlo con el reproductor. Se sirve desde
# aquí (una respuesta HTTP real, no `srcdoc`/`blob:`) porque esos dos heredan la CSP estricta del documento que
# los crea — bloquearía silenciosamente TODO script inline, tanto este harness como el código del agente. Las
# rutas `/api/` no llevan esa CSP (ver `api/app.py`), así que esta respuesta sí puede ejecutar scripts inline.
_LIVE_HARNESS = """<script>(function(){
  let virtualNow = 0, pending = [], nextId = 1;
  window.performance.now = function(){ return virtualNow; };
  window.requestAnimationFrame = function(cb){ const id = nextId++; pending.push([id, cb]); return id; };
  window.cancelAnimationFrame = function(id){ pending = pending.filter(function(x){ return x[0] !== id; }); };
  function tick(deltaMs){
    virtualNow += deltaMs;
    const due = pending; pending = [];
    for (const pair of due) {
      try { pair[1](virtualNow); }
      catch (e) { try { parent.postMessage({ __cutly: 'error', message: String((e && e.stack) || e) }, '*'); } catch (_e) {} }
    }
  }
  window.addEventListener('message', function(ev){
    const d = ev.data;
    if (d && d.__cutly === 'tick') tick(d.ms);
  });
  // 'ready' SOLO tras `load`: si se avisa nada más ejecutarse este script (en <head>), el <script> de la
  // escena (en <body>, se ejecuta después) aún no ha llamado a su primer requestAnimationFrame — la ráfaga
  // de ticks que dispara el editor al recibir 'ready' (para saltar al instante correcto) llegaría con
  // `pending` vacío y se perdería casi entera, dejando la animación congelada cerca del principio pase lo
  // que pase. Confirmado con la escena real de producción: se quedaba en el primer fotograma sin avanzar.
  window.addEventListener('load', function(){
    try { parent.postMessage({ __cutly: 'ready' }, '*'); } catch (e) {}
  });
})();</script>"""
_HEAD_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)
_HTML_RE = re.compile(r"<html[^>]*>", re.IGNORECASE)


def _inject_live_harness(code: str, params: dict | None = None, words: list | None = None) -> str:
    from cutly.services.scene_js.renderer import params_script

    head = _LIVE_HARNESS + f"<script>{params_script(params or {}, words)}</script>"
    if _HEAD_RE.search(code):
        return _HEAD_RE.sub(lambda m: m.group(0) + head, code, count=1)
    if _HTML_RE.search(code):
        return _HTML_RE.sub(lambda m: m.group(0) + head, code, count=1)
    return head + code


class SceneSource(BaseModel):
    template: str | None = Field(None, description="Nombre de plantilla (GET /scenes/templates)")
    params: dict[str, Any] = Field(default_factory=dict)
    scene: dict[str, Any] | None = Field(None, description="Escena completa escrita a mano (alternativa a template)")
    code: str | None = Field(
        None, max_length=300_000, description="HTML/JS autocontenido (motor de navegador, alternativa a template/scene)"
    )
    duration: float = Field(
        10, ge=0.5, le=120, description="Duración de la capa en segundos (las plantillas se ajustan a ella)"
    )
    words: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=5000,
        description="Solo con `code`: palabras de prueba [{w,start,end}] (s desde el inicio de la capa) -> window.CUTLY_WORDS",
    )

    @property
    def is_code(self) -> bool:
        return self.code is not None


class PreviewBody(SceneSource):
    times: list[float] = Field(
        default_factory=lambda: [0.5], max_length=MAX_TIMES, description="Instantes (s desde el inicio de la capa)"
    )
    width: int = Field(960, ge=160, le=1920, description="Ancho en píxeles de CADA fotograma")
    height: int | None = Field(None, ge=160, le=1920, description="Solo con `code`: por defecto, vertical 9:16")
    fit: str = Field("contain", pattern="^(contain|cover)$")
    cols: int = Field(3, ge=1, le=6)
    fps: int = Field(30, ge=5, le=60, description="Solo con `code`: a qué ritmo se simula la animación")
    transparent: bool = Field(False, description="Solo con `code`: simula con fondo transparente (se muestra sobre un damero)")


def _check_source(src: SceneSource) -> None:
    n = sum(x is not None for x in (src.template, src.scene, src.code))
    if n != 1:
        raise HTTPException(422, "Indica exactamente una de: `template` (+ `params`), `scene` o `code`")


def resolve_scene(src: SceneSource) -> Scene:
    """Solo para `template`/`scene` (devuelve el objeto declarativo); `code` no tiene equivalente JSON."""
    _check_source(src)
    if src.code is not None:
        raise HTTPException(422, "`code` no se puede expandir a JSON; úsalo directamente en la capa")
    try:
        if src.template is not None:
            return TP.build_template(src.template, src.params, src.duration)
        return Scene.model_validate(src.scene)
    except TP.TemplateError as e:
        raise HTTPException(422, str(e)) from e
    except ValidationError as e:
        errs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:6])
        raise HTTPException(422, f"Escena inválida: {errs}") from e


@router.get("/scenes/templates")
def list_templates(q: str | None = None, _: Principal = Depends(require_read)):
    """Plantillas de animación disponibles, con sus parámetros y una capa `scene` de ejemplo lista para `add_layer`."""
    out = [TP.describe(t) for t in TP.REGISTRY.values()]
    if q:
        ql = q.lower()
        out = [t for t in out if ql in " ".join([t["name"], t["title"], t["description"], *t["tags"]]).lower()]
    return {"templates": out}


@router.get("/scenes/templates/{name}")
def describe_template(name: str, _: Principal = Depends(require_read)):
    try:
        return TP.describe(TP.get_template(name))
    except TP.TemplateError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/scenes/build")
def build_scene(body: SceneSource, _: Principal = Depends(require_read)):
    """Expande una plantilla a su escena completa (JSON editable): úsala como punto de partida para personalizarla
    y ponla en `layer.scene` (con `template` vacío)."""
    return resolve_scene(body).model_dump(mode="json", exclude_none=True)


@router.get("/scenes/schema")
def scene_schema(_: Principal = Depends(require_read)):
    """JSON Schema completo de una escena (objetos node/text/card/link/dot/ring/burst/meter, cámara, fondo)."""
    return Scene.model_json_schema()


def _checker(size: tuple[int, int], cell: int = 24) -> Image.Image:
    img = Image.new("RGBA", size, (58, 62, 74, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(88, 93, 108, 255))
    return img


def _sheet(frames: list[Image.Image], times: list[float], cols: int) -> Response:
    n = len(frames)
    cols = min(cols, n) or 1
    rows = -(-n // cols)
    w, h = frames[0].size
    sheet = Image.new("RGB", (cols * w, rows * h), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, fr in enumerate(frames):
        if fr.mode == "RGBA":  # escena transparente: damero para distinguir lo vacío de lo negro
            fr = Image.alpha_composite(_checker(fr.size), fr).convert("RGB")
        sheet.paste(fr, ((i % cols) * w, (i // cols) * h))
        if n > 1:
            d.text(((i % cols) * w + 8, (i // cols) * h + 6), f"t={times[i]:g}s", fill=(255, 255, 255))
    buf = io.BytesIO()
    sheet.save(buf, "PNG", compress_level=3)
    return Response(buf.getvalue(), media_type="image/png")


@router.post("/scenes/preview")
def preview(body: PreviewBody, _: Principal = Depends(require_write)):
    """PNG con uno o varios fotogramas de una escena (hoja de contacto si hay varios `times`): el bucle de
    diseño de una animación sin montar un proyecto. Los tiempos van desde el inicio de la capa.

    Con `code`, cada fotograma tarda de verdad (se simula la animación paso a paso desde el principio): pide
    pocos instantes y no abuses de esta llamada mientras iteras."""
    _check_source(body)
    if not _busy.acquire(timeout=20):
        raise HTTPException(503, "Hay otra vista previa en curso; reintenta en unos segundos")
    try:
        if body.code is not None:
            from cutly.services.scene_js.renderer import JsSceneError, render_js_preview

            w = body.width
            h = body.height or round(w * 16 / 9)
            try:
                frames = render_js_preview(body.code, w, h, [max(0.0, t) for t in body.times], body.fps, body.params, body.words, body.transparent)
            except JsSceneError as e:
                raise HTTPException(422, str(e)) from e
            except ImportError as e:
                raise HTTPException(503, f"Este servidor no tiene instalado el motor de navegador ({e})") from e
            if not frames:
                raise HTTPException(422, "Ningún instante pedido cayó dentro de la animación")
            return _sheet(frames, sorted(set(round(max(0.0, t), 3) for t in body.times)), body.cols)
        scene = resolve_scene(body)
        w = body.width
        h = max(2, round(w * scene.world.h / scene.world.w))
        pl = Player(scene, w, h, body.fit)
        frames = [Image.fromarray(pl.frame(max(0.0, t))).convert("RGB") for t in body.times]
        return _sheet(frames, body.times, body.cols)
    finally:
        _busy.release()


_KIT_DIR = Path(__file__).resolve().parents[2] / "services" / "scene_js" / "kit"

# Reglas que una escena `code` debe cumplir para verse bien en un móvil. `/scenes/lint` comprueba la mayoría.
_CODE_RULES = [
    "Mide TODO con u = innerWidth/1080 (no uses px fijos): la misma escena sirve a 1080x1920, 540x960 o 1920x1080.",
    "Texto legible en móvil: titulares ≥ 3% del ancho (≈34 px a 1080), cuerpo ≥ 2,2% (≈24 px). Nunca por debajo.",
    "Márgenes seguros: 6% a cada lado; nada importante en el 18% inferior (botones de la app) ni en el 8% superior.",
    "Texto largo: mídelo con ctx.measureText y pártelo en líneas (la plantilla trae wrap()); la píldora/rótulo se ajusta al texto.",
    "Reloj: solo requestAnimationFrame(now)/performance.now(). Prohibido Date.now, setTimeout/setInterval y @keyframes/transition de CSS.",
    "Sin red ni recursos remotos (fuentes, imágenes, fetch), sin WebGL, sin localStorage: todo inline. Emoji y Unicode funcionan.",
    "Por defecto el fondo se renderiza opaco (tapa el vídeo en su caja). Con `transparent: true` en la capa no pintes fondo (ni body{background} ni fillRect a pantalla completa) y se ve el vídeo de detrás. Para títulos animados usa POST /projects/{id}/title.",
    "Fuentes: Inter, Inter SemiBold/ExtraBold, Montserrat, Anton, Bebas Neue, Poppins y las subidas están disponibles por nombre (font-family) sin incrustarlas.",
    "Sin Math.random en el dibujo (usa un generador determinista): así dos renders dan lo mismo y las partículas no parpadean.",
    "Parámetros editables (textos, colores) en window.CUTLY_PARAMS = layer.params; define valores por defecto con Object.assign.",
    "Duración total de las sub-escenas ≤ end-start de la capa (máx. 30 s; ideal 8-15 s, una idea por escena). Menos fps (15-20) = render más rápido.",
    "Bucle de iteración: escribe → POST /scenes/lint (barato) → POST /scenes/preview con 3-5 instantes (aspecto) → add_layer.",
]


@router.get("/scenes/code-kit")
def code_kit(_: Principal = Depends(require_read)):
    """Todo lo necesario para escribir una escena `code` bien: reglas, y una plantilla base completa (HTML) con
    layout responsivo, fondo con partículas, rótulo inferior que se ajusta al texto, nodos, flujo y
    tarjetas, todo parametrizado con `window.CUTLY_PARAMS`. Copia `base_html`, cambia `P` y `SCENES`, y valida."""
    return {
        "rules": _CODE_RULES,
        "params_global": "window.CUTLY_PARAMS (= layer.params, objeto JSON; siempre existe, puede ser {})",
        "workflow": ["POST /scenes/lint", "POST /scenes/preview (code, times)", "add_layer {type:scene, code, params, start, end}"],
        "base_html": (_KIT_DIR / "base.html").read_text(),
        "kinetic_html": (_KIT_DIR / "kinetic.html").read_text(),  # base TRANSPARENTE de títulos cinéticos (copiable para algo a medida)
    }


class LintBody(BaseModel):
    code: str = Field(..., max_length=300_000)
    params: dict[str, Any] = Field(default_factory=dict, description="Se expone en la escena como window.CUTLY_PARAMS")
    width: int = Field(1080, ge=160, le=1920, description="Ancho REAL de salida de la capa (para medir legibilidad)")
    height: int = Field(1920, ge=160, le=1920)
    duration: float = Field(10, ge=0.5, le=120, description="`end - start` de la capa en segundos")
    fps: int = Field(20, ge=5, le=30)
    words: list[dict[str, Any]] = Field(default_factory=list, max_length=5000, description="Palabras de prueba para CUTLY_WORDS")


@router.post("/scenes/lint")
def lint(body: LintBody, _: Principal = Depends(require_write)):
    """Valida una escena `code` ejecutándola de verdad (sin guardar nada): errores de JS, lienzo vacío o estático,
    red/WebGL/almacenamiento, `Date.now`/`setTimeout`/animaciones CSS que no siguen el reloj virtual, texto
    demasiado pequeño o que se sale del encuadre. Mucho más barato que `/scenes/preview`: úsala en cada iteración
    y reserva la vista previa para juzgar el aspecto. Cada `issue` trae `severity`, `code`, `message`, `suggestion`."""
    if not _busy.acquire(timeout=20):
        raise HTTPException(503, "Hay otra vista previa o validación en curso; reintenta en unos segundos")
    try:
        from cutly.services.scene_js.lint import lint_scene
        from cutly.services.scene_js.renderer import JsSceneError

        try:
            res = lint_scene(body.code, body.width, body.height, body.duration, body.params, body.fps, body.words)
        except JsSceneError as e:
            raise HTTPException(422, str(e)) from e
        except ImportError as e:
            raise HTTPException(503, f"Este servidor no tiene instalado el motor de navegador ({e})") from e
        return res.as_dict()
    finally:
        _busy.release()


@router.post("/scenes/live-doc", response_class=HTMLResponse)
def live_doc(
    code: str = Form(..., max_length=300_000),
    params: str = Form("{}", max_length=20_000),
    words: str = Form("[]", max_length=200_000),
    _: Principal = Depends(require_read),
):
    """Documento de una escena `code`, con el harness de reloj ya inyectado, para el `<iframe>` en vivo del
    editor web (`web/editor/scene-live.js`) — nunca se llama desde fuera de ahí. El editor navega un iframe
    aquí con un `<form method="POST" target="...">` (un `src="data:"/srcdoc` heredaría la CSP estricta del
    editor y bloquearía en silencio todo script inline, incluido este harness)."""
    try:
        parsed = json.loads(params)
        if not isinstance(parsed, dict):
            raise ValueError
    except ValueError:
        parsed = {}
    try:
        wl = json.loads(words)
        if not isinstance(wl, list):
            raise ValueError
        wl = [
            {"w": str(x["w"])[:60], "start": float(x["start"]), "end": float(x["end"])}
            for x in wl[:5000]
            if isinstance(x, dict) and "w" in x
        ]
    except (ValueError, KeyError, TypeError):
        wl = []
    html = _inject_live_harness(code, parsed, wl)
    resp = HTMLResponse(html)
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"  # el editor SÍ puede embeberlo (mismo origen); nadie más
    return resp
