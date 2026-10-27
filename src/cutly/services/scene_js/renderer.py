"""Escenas `code`: HTML/JS autocontenido renderizado con un navegador aislado (sin red) y reloj determinista.

El documento del agente usa `requestAnimationFrame`/`performance.now()` con total normalidad — el truco está en
`_HARNESS`, un script inyectado ANTES que cualquier otro: sustituye esas dos funciones (y `cancelAnimationFrame`)
por versiones controladas por un reloj virtual que nosotros avanzamos desde Python, un paso de `1000/fps` ms cada
vez, capturando un fotograma tras cada paso. Así el resultado es reproducible con independencia de lo lenta o
irregular que sea la máquina que renderiza (confirmado con pruebas: usar el tiempo virtual nativo de Chromium
—`Emulation.setVirtualTimePolicy`— no basta por sí solo: no garantiza un repintado del `<canvas>` por cada
`requestAnimationFrame` pendiente, así que el estado de la animación se queda parado).

La página navega a una URL `data:` (nunca `file://`, para no exponer el sistema de archivos) y toda petición de
red se aborta: el documento debe ser enteramente autocontenido (sin `<img src="https://…">`, `fetch`, fuentes
remotas…). Un bug o un documento hostil puede, como mucho, colgarse solo — nunca llegar a otra parte de la red.
"""

import base64
import io
import os
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

CHROMIUM_PATH = "/usr/bin/chromium"
# Más conservador que las plantillas declarativas (services/scene/sequence.py, 120 s / 4096²): Chromium real
# midió hasta ~860 MB de pico generando 20 s a 1080x1920 (vs 900 MB del límite del worker) y ~12x más lento
# que tiempo real. Ver docs/SCENES.md.
MAX_SECONDS = 30
MAX_PIXELS = 1920 * 1920
RENDER_TIMEOUT_S = 150  # tope para TODA la generación (arranque + simulación completa)
NAV_TIMEOUT_MS = 10_000
SHOT_TIMEOUT_MS = 45_000
MAX_PREVIEW_TIMES = 12

_FONTCONF_TMPL = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
%s</fontconfig>
"""


def _fontconfig_file() -> Path:
    """fontconfig para Chromium con las fuentes de la biblioteca (Inter, Montserrat, Anton, Bebas, Poppins…, y las
    subidas): así las escenas `code` las usan por nombre (`font-family:"Inter"`) sin incrustarlas en el HTML."""
    from cutly.config import get_settings
    from cutly.services.render.fonts import font_dirs

    dirs = "".join(f"  <dir>{d}</dir>\n" for d in font_dirs())
    conf = _FONTCONF_TMPL % dirs
    path = get_settings().data_dir / "cache" / "scene-fonts.conf"
    try:
        if not path.exists() or path.read_text() != conf:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(conf)
    except OSError:  # sin disco escribible: Chromium usa las fuentes del sistema
        return Path("/etc/fonts/fonts.conf")
    return path


_HARNESS = """
(function(){
  let virtualNow = 0;
  let pending = [];
  let nextId = 1;
  window.performance.now = function(){ return virtualNow; };
  window.requestAnimationFrame = function(cb){ const id = nextId++; pending.push([id, cb]); return id; };
  window.cancelAnimationFrame = function(id){ pending = pending.filter(function(x){ return x[0] !== id; }); };
  window.__cutlyTick = function(deltaMs){
    virtualNow += deltaMs;
    const due = pending; pending = [];
    for (const pair of due) {
      try { pair[1](virtualNow); } catch (e) { return String((e && e.stack) || e); }
    }
    return null;
  };
})();
"""


def params_script(params: dict, words: list[dict] | None = None) -> str:
    """JS que expone los parámetros de la capa como `window.CUTLY_PARAMS` (objeto JSON congelado) y las palabras
    dichas durante la capa como `window.CUTLY_WORDS` (`[{w,start,end}]`, segundos desde el inicio de la capa). Se escapa `<`
    para que un valor con `</script>` no pueda cerrar la etiqueta cuando se incrusta en un documento HTML."""
    import json

    blob = json.dumps(params, ensure_ascii=False)
    blob = blob.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    wblob = json.dumps(words or [], ensure_ascii=False)
    wblob = wblob.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f"window.CUTLY_PARAMS = Object.freeze({blob}); window.CUTLY_WORDS = Object.freeze({wblob});"


class JsSceneError(ValueError):
    pass


@dataclass
class JsSceneSequence:
    pattern: str
    x: int
    y: int
    frames: int
    t0: float


def _check_html(code: str) -> None:
    if len(code) > 300_000:
        raise JsSceneError("el código de la escena es demasiado grande (máx. 300 000 caracteres)")


class _Session:
    """Una página aislada lista para simular: harness inyectado, red cortada, reloj en cero."""

    def __init__(self, code: str, width: int, height: int, params: dict | None = None, extra_init: str = "", words: list[dict] | None = None):
        _check_html(code)
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch(
                executable_path=CHROMIUM_PATH,
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
                env={**os.environ, "FONTCONFIG_FILE": str(_fontconfig_file())},
            )
        except Exception as e:  # noqa: BLE001 - Chromium no disponible o no arranca
            self._pw.stop()
            raise JsSceneError(f"no se pudo arrancar el navegador de renderizado: {e}") from e
        self.page = self.browser.new_page(viewport={"width": width, "height": height})
        self.page.set_default_timeout(NAV_TIMEOUT_MS)
        self.page.add_init_script(_HARNESS)
        # `window.CUTLY_PARAMS` siempre existe (puede ser {}): lo mismo que inyecta /scenes/live-doc en el editor
        self.page.add_init_script(params_script(params or {}, words))
        if extra_init:
            self.page.add_init_script(extra_init)
        self.page.route("**/*", lambda route: route.abort())  # sin red: ver docstring del módulo
        self.page.on("pageerror", self._on_error)
        self._js_error: str | None = None
        url = "data:text/html;charset=utf-8;base64," + base64.b64encode(code.encode("utf-8", "replace")).decode()
        try:
            self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightTimeout as e:
            self.close()
            raise JsSceneError(
                "la escena tardó demasiado en cargar (documento HTML inválido o demasiado pesado)"
            ) from e
        if self._js_error:
            err, self._js_error = self._js_error, None
            self.close()
            raise JsSceneError(f"la escena lanza un error de JavaScript nada más cargar: {err}")

    def _on_error(self, exc) -> None:
        self._js_error = str(exc)

    def tick(self, step_ms: float) -> None:
        try:
            err = self.page.evaluate("(step) => window.__cutlyTick(step)", step_ms)
        except PlaywrightError as e:
            raise JsSceneError(f"la escena lanzó un error al avanzar el tiempo: {e}") from e
        if err:
            raise JsSceneError(f"error de JavaScript durante la animación: {err}")
        if self._js_error:  # error no capturado por el harness (p. ej. fuera de cualquier rAF)
            err2, self._js_error = self._js_error, None
            raise JsSceneError(f"error de JavaScript durante la animación: {err2}")

    def _shot(self, **kw) -> Image.Image:
        # La captura puede tardar bastante en un servidor cargado y sin GPU: margen amplio y error controlado (422, no 500).
        try:
            png = self.page.screenshot(type="png", timeout=SHOT_TIMEOUT_MS, **kw)
        except PlaywrightError as e:
            raise JsSceneError(f"no se pudo capturar un fotograma (¿servidor cargado?): {str(e).splitlines()[0]}") from e
        return Image.open(io.BytesIO(png))

    def frame_rgb(self) -> Image.Image:
        return self._shot().convert("RGB")

    def frame(self, transparent: bool = False) -> Image.Image:
        """Fotograma RGB (fondo opaco) o RGBA si `transparent` (la página no pinta fondo: se ve el vídeo de detrás)."""
        if not transparent:
            return self.frame_rgb()
        return self._shot(omit_background=True).convert("RGBA")

    def close(self) -> None:
        try:
            self.browser.close()
        finally:
            self._pw.stop()


def _step_count(end: float, fps: int) -> int:
    return max(1, round(min(end, MAX_SECONDS) * fps))


def _anchor_factor(anchor: str) -> tuple[float, float]:
    h = "left" if anchor.endswith("left") else "right" if anchor.endswith("right") else "center"
    v = anchor.split("_")[0] if "_" in anchor else "center"
    return {"left": 0.0, "center": 0.5, "right": 1.0}[h], {"top": 0.0, "center": 0.5, "bottom": 1.0}[v]


def box_pixels(layer, W: int, H: int) -> tuple[int, int, int, int]:
    """(x, y, ancho, alto) de la caja en píxeles del fotograma de salida. A diferencia de las escenas
    declarativas, aquí no hay un "mundo" con proporción propia: sin `box.h`, se asume la proporción del
    propio fotograma de salida (lo normal: una escena de código a pantalla completa)."""
    b = layer.box
    bw = max(2, round(b.w * W))
    bh = max(2, round(bw * H / W)) if b.h is None else max(2, round(b.h * H))
    bw, bh = bw + bw % 2, bh + bh % 2
    fx, fy = _anchor_factor(b.anchor)
    return round(b.x * W - bw * fx), round(b.y * H - bh * fy), bw, bh


def render_js_sequence(
    layer, W: int, H: int, fps: int, outdir: Path, warnings: list[str],
    window: tuple[float, float] | None = None, words: list[dict] | None = None,
) -> JsSceneSequence | None:  # fmt: skip
    """Genera la secuencia de PNG (f%05d.png, RGB; RGBA con `layer.transparent`) de una capa `scene` con `code`.

    El estado de la animación es acumulativo (igual que un vídeo grabado, no una función pura del tiempo): para
    sacar el tramo `window` hay que simular TODO desde el principio y quedarse solo con esos fotogramas. Para
    capas largas en renders por tramos esto es más caro que las plantillas declarativas; está documentado.
    """
    fps_scene = layer.fps or fps
    length = layer.end - layer.start
    total_steps = _step_count(length, fps_scene)
    if length > MAX_SECONDS:
        warnings.append(f"La escena de código '{layer.id}' se limita a {MAX_SECONDS} s")
    x0, y0, bw, bh = box_pixels(layer, W, H)
    if bw * bh > MAX_PIXELS:
        warnings.append(f"La escena de código '{layer.id}' es demasiado grande ({bw}x{bh}): no se renderiza")
        return None
    if x0 >= W or y0 >= H or x0 + bw <= 0 or y0 + bh <= 0:
        warnings.append(f"La escena de código '{layer.id}' queda fuera de la pantalla: no se renderiza")
        return None
    i0, i1 = 0, total_steps + 1
    if window:
        i0 = max(0, int((window[0] - layer.start) * fps_scene) - 1)
        i1 = min(i1, int((window[1] - layer.start) * fps_scene) + 2)
        if i1 <= i0:
            return None
    step_ms = 1000.0 / fps_scene
    outdir.mkdir(parents=True, exist_ok=True)
    t_deadline = time.time() + RENDER_TIMEOUT_S
    try:
        session = _Session(layer.code, bw, bh, layer.params, words=words)
    except JsSceneError as e:
        warnings.append(f"Escena de código '{layer.id}' ignorada: {e}")
        return None
    try:
        n = 0
        for i in range(i1):
            if time.time() > t_deadline:
                raise JsSceneError(f"la escena tarda demasiado en generarse (más de {RENDER_TIMEOUT_S} s)")
            session.tick(step_ms)
            if i < i0:
                continue
            session.frame(layer.transparent).save(outdir / f"f{n:05d}.png", compress_level=1)
            n += 1
    except JsSceneError as e:
        warnings.append(f"Escena de código '{layer.id}' interrumpida: {e}")
        if n == 0:
            return None
    finally:
        session.close()
    return JsSceneSequence(str(outdir / "f%05d.png"), x0, y0, n, i0 / fps_scene)


def render_js_preview(
    code: str, width: int, height: int, times: list[float], fps: int, params: dict | None = None,
    words: list[dict] | None = None, transparent: bool = False,
) -> list[Image.Image]:  # fmt: skip
    """Fotogramas sueltos para `POST /scenes/preview`: simula desde 0 hasta el mayor `t` pedido."""
    if len(times) > MAX_PREVIEW_TIMES:
        raise JsSceneError(f"máximo {MAX_PREVIEW_TIMES} instantes por vista previa")
    if width * height > MAX_PIXELS:
        raise JsSceneError(f"la vista previa es demasiado grande (máx. {MAX_PIXELS} píxeles)")
    targets = sorted(set(round(max(0.0, t), 3) for t in times))
    last_t = min(targets[-1] if targets else 0.0, MAX_SECONDS)
    step_ms = 1000.0 / fps
    out: dict[float, Image.Image] = {}
    t_deadline = time.time() + RENDER_TIMEOUT_S
    session = _Session(code, width, height, params, words=words)
    try:
        t = 0.0
        pending = list(targets)
        while pending and t <= last_t + step_ms / 1000:
            if time.time() > t_deadline:
                raise JsSceneError(f"la vista previa tarda demasiado en generarse (más de {RENDER_TIMEOUT_S} s)")
            session.tick(step_ms)
            t += step_ms / 1000
            while pending and t >= pending[0]:
                out[pending.pop(0)] = session.frame(transparent)
    finally:
        session.close()
    return [out[tt] for tt in targets if tt in out]
