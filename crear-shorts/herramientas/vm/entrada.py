"""ACTUAR con ritmo humano: ratón (trayectos curvos) y teclado (ritmo variable, errores corregidos), siempre con la
guarda de foco. Los planes se ejecutan EN el invitado con un reproductor sin deriva (un SSH por plan)."""
import json
import os
import random
import shlex
import time

import mover
import ocr_buscar
import tipear

from .config import TMP, die
from .conexion import ssh
from .pantalla import _ocr_words, shot
from .registro import logged


_pos_cache = {}


def pos(fresh=False):
    if _pos_cache and not fresh:
        return _pos_cache["p"]
    out = ssh("xdotool getmouselocation --shell", capture=True)
    d = dict(l.split("=") for l in out.splitlines() if "=" in l)
    _pos_cache["p"] = (int(d["X"]), int(d["Y"]))
    return _pos_cache["p"]


def active_title():
    return ssh("xdotool getactivewindow getwindowname 2>/dev/null", capture=True, check=False)


def require_focus(title):
    if title and title.lower() not in active_title().lower():
        die(f"FOCO INCORRECTO: '{active_title()}' (esperado '{title}') — NO escribo")


# El plan se compila a una LÍNEA DE TIEMPO absoluta (t en segundos) y un reproductor local la ejecuta sin deriva:
# a diferencia de `sleep` encadenados, el tiempo que tarda cada xdotool no se acumula. Un único SSH por plan.
PLAYER = r'''
import json, subprocess, sys, time
ev = json.load(sys.stdin)
t0 = time.monotonic()
for e in ev:
    wait = e["t"] - (time.monotonic() - t0)
    if wait > 0:
        time.sleep(wait)
    op = e["op"]
    if op == "m":
        subprocess.run(["xdotool", "mousemove", str(e["x"]), str(e["y"])])
    elif op == "k":
        subprocess.run(["xdotool", "type", "--delay", str(e["delay"]), "--", e["c"]])
    elif op == "key":
        subprocess.run(["xdotool", "key", e["name"]])
'''


def compile_plan(plan):
    """Convierte un plan (k/bs/ret/tab/d/m) en la línea de tiempo del reproductor."""
    t, out = 0.0, []
    for e in plan:
        if e[0] == "k":
            # No ASCII: xdotool reasigna una tecla al vuelo; con delay 0 la restaura antes de que la app la lea
            # y el carácter se pierde (medido: ≥ 30 ms acierta; doc 08 nº 39).
            out.append({"t": t, "op": "k", "c": e[1], "delay": 0 if ord(e[1]) < 128 else 40})
        elif e[0] in ("bs", "ret", "tab"):
            out.append({"t": t, "op": "key", "name": {"bs": "BackSpace", "ret": "Return", "tab": "Tab"}[e[0]]})
        elif e[0] == "d":
            t += e[1]
        elif e[0] == "m":
            out.append({"t": t, "op": "m", "x": e[1], "y": e[2]})
    return out


def play(plan):
    ev = compile_plan(plan)
    payload = json.dumps(ev)
    # timeout proporcional a la duración real del plan: un comando largo (p. ej. 140+ caracteres a 42 wpm)
    # tarda de verdad más de los 25s por defecto de ssh() — no es un cuelgue, es tecleo humano real.
    dur = ev[-1]["t"] if ev else 0
    # el reproductor va por -c y el plan por stdin del propio python (bash -s ya usa stdin para el script)
    ssh("python3 -c %s <<'__PLAN__'\n%s\n__PLAN__\n" % (shlex.quote(PLAYER), payload),
        timeout=max(25, dur + 15))
    for e in reversed(ev):
        if e["op"] == "m":
            _pos_cache["p"] = (e["x"], e["y"])
            break


@logged("move")
def move(x, y, dur=None, seed=None):
    x0, y0 = pos()
    pts = mover.trayecto(x0, y0, x, y, dur, random.Random(seed))
    plan = []
    for px, py in pts:
        plan += [("m", px, py), ("d", 0.022)]
    play(plan)


@logged("click")
def click(dc=False):
    ssh("xdotool click --repeat 2 --delay 60 1" if dc else "xdotool click 1")


@logged("type")
def type_human(text, wpm=55.0, typos=0.015, seed=None, in_title=None):
    require_focus(in_title)
    play(tipear.plan(text, wpm, typos, random.Random(seed)))


@logged("typeurl")
def typeurl(url, wpm=45.0, in_title=None):
    # El navegador autocompleta con el historial y Enter iría a lo autocompletado (doc 07 nº 29):
    # Suprimir quita la sugerencia y no toca nada si no hay.
    require_focus(in_title)
    ssh("xdotool key ctrl+l")
    time.sleep(0.4)
    type_human(url, wpm=wpm, typos=0.02)
    time.sleep(0.3)
    ssh("xdotool key Delete")
    time.sleep(0.2)
    ssh("xdotool key Return")


def _find(word, n, sub, thorough=False, reg=None):
    lines = _ocr_words(shot(os.path.join(TMP, "_vmct.png")), region=reg, thorough=thorough).splitlines(True)
    t = ocr_buscar.norm(word)
    for modo in ("exacta", "contiene"):
        r = ocr_buscar.buscar(lines, t, n, 1.0, reg, sub, modo)
        if r:
            return tuple(int(v) for v in r.split(","))
    return None


@logged("clicktext")
def clicktext(word, n=1, dc=False, sub="", seg=6, reg=None):
    t0 = time.time()
    while time.time() - t0 < seg:
        p = _find(word, n, sub, reg=reg) or _find(word, n, sub, thorough=True, reg=reg)
        if p:
            move(*p)
            time.sleep(0.25)
            click(dc)
            return p
        time.sleep(0.5)
    die(f"no encontré '{word}' en la pantalla del invitado tras {seg}s")


@logged("clickimg")
def clickimg(template, dc=False, thr=0.85, seg=6):
    """Clic en una imagen de referencia (botón que el OCR no lee, p. ej. 'I Accept' blanco sobre naranja)."""
    try:
        import cv2
    except ImportError:
        die("clickimg requiere opencv: pip install opencv-python")
    tpl = cv2.imread(template, cv2.IMREAD_COLOR)
    if tpl is None:
        die(f"no puedo leer la plantilla {template}")
    t0 = time.time()
    while time.time() - t0 < seg:
        scr = cv2.imread(shot(os.path.join(TMP, "_vmimg.png")), cv2.IMREAD_COLOR)
        _, val, _, loc = cv2.minMaxLoc(cv2.matchTemplate(scr, tpl, cv2.TM_CCOEFF_NORMED))
        if val >= thr:
            p = (loc[0] + tpl.shape[1] // 2, loc[1] + tpl.shape[0] // 2)
            move(*p)
            time.sleep(0.25)
            click(dc)
            return p
        time.sleep(0.5)
    die(f"no encontré la imagen {template} (mejor coincidencia {val:.2f} < {thr})")


def _find_detail(word, n, sub, reg=None, seg=6):
    """Como _find pero devuelve (cx, cy, ancho_de_carácter) del trozo buscado; reintenta (el OCR es irregular)."""
    t0 = time.time()
    t = ocr_buscar.norm(word)
    while time.time() - t0 < seg:
        for thorough in (False, True):
            lines = _ocr_words(shot(os.path.join(TMP, "_vmsel.png")), region=reg, thorough=thorough).splitlines(True)
            for modo in ("exacta", "contiene"):
                r = ocr_buscar.buscar(lines, t, n, 1.0, reg, sub, modo, detail=True)
                if r:
                    return r
        time.sleep(0.4)
    return None


@logged("selecttext")
def selecttext(word, n=1, sub="", tries=3, reg=None):
    """Selecciona un trozo de texto con TECLADO: clic junto al final del trozo + Shift+←×len. Después comprueba
    QUÉ quedó seleccionado (selección PRIMARY de X11, con centinela previo) y reintenta con otro desplazamiento.
    Medido en Burp/Java: el doble clic de xdotool NO selecciona de forma fiable y el Ctrl+C no llega al portapapeles;
    en cambio clic + Shift+← selecciona siempre y deja PRIMARY actualizada. xclip va con >/dev/null 2>&1: sin eso
    retiene el SSH y cuelga el guion."""
    want = sub or word
    got = ""
    d = _find_detail(word, n, want, reg) or (_find_detail(want, n, "", reg) if want != word else None)
    if not d:
        die(f"no encontré '{word}' para seleccionar")
    cx, cy, cw = d
    for off in (0.35, 0.15, 0.55)[:tries]:
        ssh("printf '__cutly__' | xclip -selection primary >/dev/null 2>&1", check=False)
        move(int(cx + len(want) * cw / 2 + off * cw), int(cy))
        time.sleep(0.3)
        click()
        time.sleep(0.3)
        ssh("xdotool key --delay 70 " + " ".join(["shift+Left"] * len(want)))
        time.sleep(0.4)
        got = ssh("xclip -selection primary -o 2>/dev/null", capture=True, check=False)
        if got == want:
            return True
    die(f"no pude seleccionar '{want}' tras {tries} intentos (última selección: {got[:30]!r})")


def type_in(wid, text, wpm=45.0, typos=0.015, seed=None):
    """type_human pero exigiendo foco por ID de ventana (no por título: ver launch_terminal)."""
    cur = ssh("xdotool getactivewindow 2>/dev/null", capture=True, check=False)
    if cur != str(wid):
        die(f"FOCO INCORRECTO: ventana activa {cur} (esperada {wid}) — NO escribo")
    play(tipear.plan(text, wpm, typos, random.Random(seed)))
