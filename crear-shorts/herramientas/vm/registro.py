"""Registro de la toma (contrato con la edición: nucleo/toma.py). Cada acción decorada con @logged deja una línea
JSONL con su instante en el vídeo; `focus` y `mark` dicen a la edición qué encuadrar y dónde empieza cada acto."""
import functools
import json
import time

from .config import STATE_FILE


def _state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(d):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f)


def _log(**ev):
    """Añade una línea JSONL al registro de la toma abierta (si no hay ninguna, no hace nada)."""
    st = _state()
    if not st.get("log"):
        return
    now = time.time()
    ev["t_wall"] = round(now, 3)
    if st.get("rec_t0"):
        ev["t_video"] = round(now - st["rec_t0"], 2)     # segundos desde el inicio del vídeo (±0,3 s)
    with open(st["log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def logged(name):
    """Decorador: registra cada acción con inicio, duración y resultado."""
    def deco(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            t0 = time.time()
            try:
                r = fn(*a, **k)
                _log(op=name, args=[str(x)[:80] for x in a], dur=round(time.time() - t0, 2), ok=True)
                return r
            except SystemExit as e:
                _log(op=name, args=[str(x)[:80] for x in a], dur=round(time.time() - t0, 2), ok=False, error=str(e)[:200])
                raise
        return w
    return deco


def focus(x, y, why="", w=None, h=None):
    """Dice a la EDICIÓN dónde está lo importante ahora (en píxeles del invitado). short_desde_toma.py
    encuadra el Short alrededor de este punto. waitfor lo registra solo (dónde apareció el texto).

    Con `w,h` (REGIÓN, p. ej. el rectángulo exacto de una ventana de terminal) la edición usa LETTERBOX de
    esa región completa — nunca recorta. SIN `w,h` (un punto suelto) usa un recorte centrado de tamaño fijo
    (896×962), que SÍ puede dejar fuera el borde de una ventana más ancha.

    REGLA: para cualquier terminal/texto que pueda ocupar TODO el ancho de su ventana, pasa SIEMPRE `w,h`
    (la geometría con la que la colocaste, p. ej. `place_id`) justo tras darle el foco y ANTES de teclear.
    El ratón no se mueve mientras se teclea, así que un `focus` sin región (basado en un punto fijo) no
    sabe que el texto puede llegar hasta el borde derecho — cortaba comandos largos (medido: sshole-run7,
    "22/tcp" salía como "cp" y "172.17.0.2" como "2.17.0.2"). Reserva el punto suelto para un énfasis
    puntual (un clic, un resultado corto) donde SÍ sabes que todo lo importante cabe en 896×962."""
    args = [int(x), int(y)]
    if w and h:
        args += [int(w), int(h)]
    _log(op="focus", args=args, why=why)


def mark(label):
    _log(op="mark", label=label)
