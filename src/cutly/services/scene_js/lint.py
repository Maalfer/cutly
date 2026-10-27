"""Validación rápida de una escena `code` ANTES de montarla: `POST /scenes/lint`.

Un agente que escribe HTML/Canvas a ciegas falla casi siempre por lo mismo: un error de JS que deja el lienzo
vacío, código que no sigue el reloj virtual (`Date.now`, `setTimeout`, animaciones CSS: en el render se quedan
quietas), peticiones de red (bloqueadas), texto ilegible en un móvil o que se sale del encuadre. Esto lo detecta
ejecutando la escena de verdad (sin guardar fotogramas salvo unas pocas muestras) y devuelve avisos accionables.

Cuesta bastante menos que una vista previa: simula la animación a pocos fps y solo hace unas 5 capturas.
"""

import re
import time
from dataclasses import dataclass, field

import numpy as np

from cutly.services.scene_js.renderer import (
    MAX_PIXELS,
    MAX_SECONDS,
    RENDER_TIMEOUT_S,
    JsSceneError,
    _Session,
)

# Texto más pequeño que esto (fracción del ancho del fotograma) cuesta leerlo en un móvil: 24 px a 1080 de ancho.
MIN_TEXT_FRAC = 0.022
LINT_FPS = 20  # 1/20 s = 0.05 s: coincide con el tope de dt (0.05) que usan los bucles típicos, sin perder pasos

# Se instala ANTES que el código del agente (add_init_script, tras el reloj virtual). Solo observa: no cambia nada.
_LINT_HOOKS = """
(function(){
  const L = window.__lint = { texts: {}, ntexts: 0, dateNow: 0, timers: 0, rafs: 0, errors: [] };
  const rafOrig = window.requestAnimationFrame;
  window.requestAnimationFrame = function(cb){ L.rafs++; return rafOrig.call(window, cb); };
  const dn = Date.now; Date.now = function(){ L.dateNow++; return dn.call(Date); };
  for (const n of ['setTimeout', 'setInterval']) {
    const o = window[n]; window[n] = function(){ L.timers++; return o.apply(window, arguments); };
  }
  window.addEventListener('unhandledrejection', function(e){ L.errors.push('promesa rechazada: ' + String(e.reason)); });
  const CP = CanvasRenderingContext2D.prototype;
  function rec(ctx, text, x, y){
    if (ctx.globalAlpha < 0.3) return;
    const cv = ctx.canvas, r = cv.getBoundingClientRect();
    if (!r.width || !cv.width) return;
    const m = ctx.getTransform(), k = r.width / cv.width;
    const px = parseFloat((/(\\d+(?:\\.\\d+)?)px/.exec(ctx.font) || [])[1]);
    if (!px) return;
    const size = px * Math.hypot(m.a, m.b) * k;
    const w = ctx.measureText(text).width, al = ctx.textAlign;
    const x0 = al === 'center' ? x - w / 2 : (al === 'right' || al === 'end') ? x - w : x;
    const a = (m.a * x0 + m.c * y + m.e) * k + r.left, b = (m.a * (x0 + w) + m.c * y + m.e) * k + r.left;
    const key = text.slice(0, 48);
    let e = L.texts[key];
    if (!e) { if (L.ntexts >= 300) return; L.ntexts++; e = L.texts[key] = { text: key, draws: 0, over: 0, maxPx: 0, maxOver: 0 }; }
    e.draws++; e.maxPx = Math.max(e.maxPx, size);
    const over = Math.max(0, -Math.min(a, b), Math.max(a, b) - innerWidth);
    if (over > 2) { e.over++; e.maxOver = Math.max(e.maxOver, over); }
  }
  for (const n of ['fillText', 'strokeText']) {
    const o = CP[n];
    CP[n] = function(text, x, y){ try { rec(this, String(text), x, y); } catch (e) {} return o.apply(this, arguments); };
  }
})();
"""

# Texto del DOM (no canvas): tamaño y si se sale del viewport.
_DOM_PROBE = """
(() => {
  const out = { small: [], over: [], anims: document.getAnimations ? document.getAnimations().length : 0,
                canvases: document.querySelectorAll('canvas').length, w: innerWidth, h: innerHeight };
  for (const el of document.querySelectorAll('body *')) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity < 0.3) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const txt = el.textContent.trim().slice(0, 40);
    const fs = parseFloat(cs.fontSize);
    if (fs < innerWidth * %(min)s) out.small.push([txt, fs]);
    if (r.left < -2 || r.right > innerWidth + 2) out.over.push([txt, Math.round(Math.max(-r.left, r.right - innerWidth))]);
  }
  return out;
})()
"""

# Comprobaciones sobre el texto fuente (no hace falta ejecutar nada).
_STATIC = [
    (
        r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\b",
        "error",
        "network_api",
        "usa una API de red (fetch/XHR/WebSocket)",
        "No hay red al renderizar: todo debe ir inline en el HTML.",
    ),
    (
        r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//""",
        "error",
        "remote_asset",
        "carga un recurso remoto (src/href con URL)",
        "Se bloquea toda petición de red: incrusta imágenes como data: URI y usa fuentes del sistema.",
    ),
    (
        r"""url\(\s*["']?\s*(?:https?:)?//|@import\b""",
        "error",
        "remote_css",
        "CSS con recurso remoto (url(http…) o @import)",
        "Se bloquea toda petición de red: nada de fuentes ni imágenes remotas.",
    ),
    (
        r"\b(?:localStorage|sessionStorage|indexedDB)\b",
        "warning",
        "storage",
        "usa almacenamiento del navegador",
        "No persiste nada entre renders (y puede lanzar una excepción en el sandbox): guarda el estado en variables.",
    ),
    (
        r"\bgetContext\(\s*['\"](?:webgl2?|experimental-webgl)['\"]",
        "error",
        "webgl",
        "pide un contexto WebGL",
        "El navegador de render corre sin GPU: usa el contexto '2d'.",
    ),
]


@dataclass
class Issue:
    severity: str  # error | warning | info
    code: str
    message: str
    suggestion: str = ""

    def as_dict(self) -> dict:
        d = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class LintResult:
    issues: list[Issue] = field(default_factory=list)
    samples: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str, suggestion: str = "") -> None:
        self.issues.append(Issue(severity, code, message, suggestion))

    def as_dict(self) -> dict:
        errors = sum(i.severity == "error" for i in self.issues)
        warnings = sum(i.severity == "warning" for i in self.issues)
        return {
            "ok": errors == 0,
            "errors": errors,
            "warnings": warnings,
            "issues": [i.as_dict() for i in self.issues],
            "samples": self.samples,
            "stats": self.stats,
        }


def static_issues(code: str, res: LintResult) -> None:
    for pat, sev, key, msg, sug in _STATIC:
        if re.search(pat, code):
            res.add(sev, key, f"El código {msg}.", sug)
    if "requestAnimationFrame" not in code and "<animate" not in code:
        res.add(
            "warning",
            "no_raf",
            "No hay ningún requestAnimationFrame: la escena será una imagen fija.",
            "Anima con un bucle requestAnimationFrame(frame) que use el `now` que recibe o performance.now().",
        )


def _sample_times(duration: float) -> list[float]:
    d = max(0.5, min(duration, MAX_SECONDS))
    ts = [min(0.3, d / 4), d * 0.25, d * 0.5, d * 0.75, max(d - 0.1, 0.1)]
    out: list[float] = []
    for t in ts:
        t = round(t, 2)
        if not out or t > out[-1] + 0.05:
            out.append(t)
    return out


def _stats(img) -> dict:
    a = np.asarray(img.convert("RGB"), dtype=np.uint8)
    lit = a.max(axis=2) > 24
    h = a.shape[0]
    return {
        "nonblack_pct": round(float(lit.mean()) * 100, 1),
        "bottom_pct": round(float(lit[int(h * 0.82):].mean()) * 100, 1),
        "mean_luma": round(float(a.mean()), 1),
    }


def lint_scene(
    code: str, width: int, height: int, duration: float, params: dict | None = None, fps: int = LINT_FPS,
    words: list[dict] | None = None,
) -> LintResult:  # fmt: skip
    """Ejecuta la escena como lo haría el render y devuelve los problemas. `duration` = `end - start` de la capa."""
    res = LintResult()
    static_issues(code, res)
    if width * height > MAX_PIXELS:
        raise JsSceneError(f"el tamaño es demasiado grande (máx. {MAX_PIXELS} píxeles)")
    if duration > MAX_SECONDS:
        res.add("warning", "too_long", f"La capa dura {duration:g} s y solo se renderizan {MAX_SECONDS} s.",
                "Divídela en escenas de 8-15 s: una por idea.")  # fmt: skip
    t_deadline = time.time() + RENDER_TIMEOUT_S
    try:
        session = _Session(code, width, height, params, extra_init=_LINT_HOOKS, words=words)
    except JsSceneError as e:
        res.add("error", "load_error", str(e), "Revisa la sintaxis del HTML/JS: la escena ni siquiera arranca.")
        return res
    images = []
    try:
        targets = _sample_times(duration)
        step = 1.0 / fps
        t = 0.0
        end_t = min(duration, MAX_SECONDS)
        pending = list(targets)
        try:
            while pending and t <= end_t + step:
                if time.time() > t_deadline:
                    res.add("error", "too_slow", f"La simulación tarda más de {RENDER_TIMEOUT_S} s.",
                            "Simplifica el dibujo por fotograma (menos partículas, sin sombras/blur costosos).")  # fmt: skip
                    break
                session.tick(step * 1000)
                t += step
                while pending and t >= pending[0]:
                    tt = pending.pop(0)
                    img = session.frame_rgb()
                    images.append(img)
                    res.samples.append({"t": tt, **_stats(img)})
        except JsSceneError as e:
            res.add("error", "js_error", str(e), "Corrige el error: en el render se conservan los fotogramas previos, pero la animación se queda parada.")  # fmt: skip
        lint = session.page.evaluate("window.__lint")
        dom = session.page.evaluate(_DOM_PROBE % {"min": MIN_TEXT_FRAC})
    finally:
        session.close()

    _analyse(res, lint or {}, dom or {}, images, width, height)
    return res


def _analyse(res: LintResult, lint: dict, dom: dict, images: list, width: int, height: int) -> None:
    for msg in lint.get("errors", [])[:3]:
        res.add("error", "js_error", f"Error de JavaScript: {msg}")
    if lint.get("dateNow"):
        res.add("warning", "date_now", f"Usa Date.now() ({lint['dateNow']} llamadas): no sigue el reloj virtual.",
                "Usa performance.now() o el argumento `now` de requestAnimationFrame.")  # fmt: skip
    if lint.get("timers"):
        res.add("warning", "timers", f"Usa setTimeout/setInterval ({lint['timers']} llamadas): no avanzan con el reloj virtual.",
                "Calcula todo con el tiempo acumulado del bucle requestAnimationFrame.")  # fmt: skip
    if dom.get("anims"):
        res.add("warning", "css_animations", f"Hay {dom['anims']} animaciones/transiciones CSS activas: no siguen el reloj virtual y saldrán quietas en el render.",
                "Anima en el bucle de requestAnimationFrame (canvas o style por JS), no con @keyframes/transition.")  # fmt: skip
    if not dom.get("canvases") and not lint.get("rafs"):
        res.add("info", "no_canvas", "No hay <canvas> ni animación por JS: se renderizará solo HTML/CSS estático.")

    if images:
        if all(s["nonblack_pct"] < 0.5 for s in res.samples):
            res.add("error", "blank", "Todas las muestras están (casi) en negro: la escena no dibuja nada visible.",
                    "Suele ser un error de JS silencioso, un canvas sin tamaño (usa innerWidth/innerHeight) o un fondo transparente: no hay canal alfa, el fondo se renderiza opaco.")  # fmt: skip
        elif len(images) > 1:
            diffs = [float((np.abs(np.asarray(a, dtype=np.int16) - np.asarray(b, dtype=np.int16)).max(axis=2) > 10).mean()) for a, b in zip(images, images[1:])]
            if max(diffs) < 0.0003:  # < 0,03% de los píxeles cambia entre muestras
                res.add("warning", "static", "La imagen no cambia entre las muestras: no hay animación visible.",
                        "Comprueba que el bucle se re-solicita (requestAnimationFrame(frame) al final de frame) y que el estado depende del tiempo.")  # fmt: skip

    minpx = width * MIN_TEXT_FRAC
    small = sorted(
        ((e["maxPx"], e["text"]) for e in (lint.get("texts") or {}).values() if e["maxPx"] < minpx),
    )
    small += [(fs, t) for t, fs in dom.get("small", [])]
    if small:
        ej = "; ".join(f"«{t}» ({px:.0f} px)" for px, t in small[:5])
        res.add("warning", "small_text", f"{len(small)} texto(s) por debajo de {minpx:.0f} px ({MIN_TEXT_FRAC * 100:g}% del ancho, {width} px): cuesta leerlos en un móvil. Ej.: {ej}",
                "Súbelos a ≥ 3% del ancho (≈32 px a 1080) para titulares y ≥ 2,2% como mínimo para el resto. Pon los tamaños en función de innerWidth, no en px fijos.")  # fmt: skip
    over = [e for e in (lint.get("texts") or {}).values() if e["draws"] and e["over"] / e["draws"] > 0.7]
    over_dom = dom.get("over", [])
    if over or over_dom:
        ej = "; ".join(f"«{e['text']}» (+{e['maxOver']:.0f} px)" for e in over[:4]) + "; ".join(f"«{t}» (+{o} px)" for t, o in over_dom[:4])
        res.add("warning", "text_overflow", f"Texto que se sale del encuadre ({width} px de ancho): {ej}",
                "Mide con ctx.measureText y reduce la fuente o parte el texto en líneas hasta que quepa con margen (≥ 5% a cada lado).")  # fmt: skip
    res.stats = {
        "viewport": [width, height],
        "text_draws": sum(e["draws"] for e in (lint.get("texts") or {}).values()),
        "min_text_px": round(min((e["maxPx"] for e in (lint.get("texts") or {}).values()), default=0), 1),
        "raf_calls": lint.get("rafs", 0),
    }
