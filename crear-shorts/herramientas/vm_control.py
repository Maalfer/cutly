#!/usr/bin/env python3
"""
vm_control.py — Controla una VM Linux (X11) de VirtualBox con entrada HUMANA, desde CUALQUIER anfitrión
(Windows, macOS o Linux). Es la "mano" de la IA: ve (capturas de VBoxManage), actúa (xdotool en el invitado,
por SSH) y verifica (OCR / plantillas / log del lab).

ESTÁNDAR DEL REPO: todas las tomas se hacen DENTRO de la VM (ver METODOLOGIA/00-empezar-aqui-vm.md).

Requisitos en el ANFITRIÓN: VBoxManage (se localiza solo, ver find_vboxmanage), ssh (OpenSSH; viene con
Windows 10/11), python3 y un OCR (Tesseract en cualquier SO; Vision de macOS si existe ctrl-kit).
Opcionales: Pillow (OCR por región), opencv-python (clickimg: búsqueda por plantilla).
Requisitos en el INVITADO: Guest Additions, sshd, xdotool, xclip, ffmpeg (para grabar), sesión X11.

Primera vez (una sola):  vm_control.py bootstrap
Variables: VM_NAME (kali) VM_KEY (~/.ssh/cutly_vm) VM_SSH_PORT (2222) VM_USER (kali) VBOXMANAGE (ruta)
           VM_OCR=tesseract (fuerza Tesseract) VM_GUEST_PASS (contraseña del invitado, SOLO si la das tú,
           para instalar la clave con `guestcontrol`; el script nunca adivina contraseñas)

CICLO DE VIDA
  start | stop | status | bootstrap
  suspend | resume                      guardar el estado (savestate) y reanudarlo en segundos: no es un snapshot
  res W H                               resolución del invitado (setvideomodehint) — p. ej. 1080 1920 para short
VER
  shot [salida.png]                     captura del invitado (~0,08 s)
  waitfor "texto" [seg] [--region x,y,w,h]  espera (OCR) a que aparezca un texto; código 1 si TIMEOUT
  waitstill [seg]                       espera a que la pantalla deje de cambiar
  focus X Y [W H] [motivo]              marca dónde/qué encuadrar (la edición del Short usa esto; waitfor lo hace solo).
                                         CON W H (región, p. ej. una ventana entera): letterbox, SIN recortar — úsalo
                                         siempre que el texto pueda llegar al borde (ver docstring de focus() en el código)
  windows | pos
ACTUAR (siempre con ritmo humano)
  move X Y [--dur S] [--seed N]         trayecto curvo (la posición se recuerda: sin viaje de ida y vuelta extra)
  click [dc]
  clicktext PALABRA [n] [dc] [--sub TROZO] [--region x,y,w,h]   (region: solo busca ahí; n=-1 la última)
  clickimg plantilla.png [dc]           clic en una imagen (botones que el OCR no lee; requiere opencv)
  selecttext PALABRA [n] --sub TROZO
  type "texto" [--wpm 55] [--typos 0.015] [--seed N] [--in "Título"]
  typeurl URL [--wpm 45] [--in "Título"]
  key Return | ctrl+alt+t ...
VERIFICAR SIN OCR
  labcheck "GET /cuenta?id=1002" [seg]  espera a que el lab haya servido esa petición (log del servidor)
TOMA: REGISTRO Y GRABACIÓN (conecta con la Fase 2: editar)
  take start NOMBRE                     abre el registro de la toma (JSONL con la hora de cada paso)
  mark "Acto 1: login"                  marca un momento del guion (aparece en el mapa de edición)
  rec start [W H FPS] [--guest] | rec stop   graba con VirtualBox en el ANFITRIÓN (cursor incluido, sin SSH); --guest: ffmpeg dentro
  take end                              cierra el registro, trae el vídeo y escribe el mapa de edición (.md)
  mapa NOMBRE                           regenera el mapa de edición desde el registro
ESTADO DE PARTIDA
  prepare [--cold]                      lab + Burp + Firefox demo; intenta reanudar el estado guardado
APPS Y VENTANAS
  put LOCAL REMOTO | get REMOTO LOCAL   copiar ficheros (scp)
  launch "cmd" | activate "Título" | place "Título" X Y W H | run "cmd"

`--in "Título"` es la GUARDA DE FOCO: si la ventana activa no contiene ese título, NO escribe.
"""
import functools
import glob
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

try:  # la consola de Windows (cp1252) no imprime tildes/emoji del invitado: forzar UTF-8 con reemplazo
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tipear   # noqa: E402  plan() de pulsaciones humanas
import mover    # noqa: E402  trayecto() de ratón humano
import ocr_buscar  # noqa: E402

VM = os.environ.get("VM_NAME", "kali")
KEY = os.environ.get("VM_KEY", os.path.expanduser("~/.ssh/cutly_vm"))
PORT = os.environ.get("VM_SSH_PORT", "2222")
USER = os.environ.get("VM_USER", "kali")
TMP = tempfile.gettempdir()
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
STATE_FILE = os.path.join(TMP, "cutly_take.json")
IS_WIN = os.name == "nt"


def die(msg):
    sys.exit(f"[vm_control] {msg}")


# ---------------------------------------------------------------- anfitrión: localizar herramientas
def find_vboxmanage():
    """VBoxManage no está en el PATH en Windows. Orden: $VBOXMANAGE, PATH, rutas típicas de cada SO."""
    cands = [os.environ.get("VBOXMANAGE"), shutil.which("VBoxManage"), shutil.which("VBoxManage.exe")]
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        if os.environ.get(var):
            cands.append(os.path.join(os.environ[var], "Oracle", "VirtualBox", "VBoxManage.exe"))
    cands += ["/usr/local/bin/VBoxManage", "/Applications/VirtualBox.app/Contents/MacOS/VBoxManage",
              "/usr/bin/VBoxManage", "/usr/lib/virtualbox/VBoxManage"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    die("no encuentro VBoxManage: instala VirtualBox o define VBOXMANAGE=<ruta> (ver PORTABILIDAD.md §Windows)")


def find_tesseract():
    c = shutil.which("tesseract") or os.path.join(os.environ.get("ProgramFiles", ""), "Tesseract-OCR", "tesseract.exe")
    return c if c and os.path.isfile(c) else None


def vbox(*args, check=True):
    return subprocess.run([find_vboxmanage(), *args], capture_output=True, text=True, check=check)


# ---------------------------------------------------------------- registro de pasos (Fase 2)
def _state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _save_state(d):
    json.dump(d, open(STATE_FILE, "w", encoding="utf-8"))


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


# ---------------------------------------------------------------- SSH (bytes: en Windows text=True rompería los \n)
def _ssh_cmd(extra=None):
    return ["ssh", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new", "-p", PORT, f"{USER}@127.0.0.1"] + (extra or [])


def ssh(script, capture=False, check=True, timeout=25):
    # LC_ALL=C.UTF-8 es IMPRESCINDIBLE: sin locale UTF-8, xdotool descarta los no ASCII (doc 08 nº 38).
    # El script va en BYTES con \n: en Windows, text=True lo convertiría a \r\n y bash fallaría.
    # `timeout` es OBLIGATORIO: subprocess.run espera a que el REMOTO cierre stdout/stderr; un proceso
    # lanzado en segundo plano que por una condición de carrera no se desengancha del todo (incluso con
    # setsid) deja el canal SSH colgado para siempre y sin avisar (medido: 3+ min sin CPU, bloqueado en
    # I/O). Mejor fallar rápido y de forma diagnosticable que colgar el guion en silencio.
    try:
        r = subprocess.run(_ssh_cmd(["export DISPLAY=:0 LC_ALL=C.UTF-8 LANG=C.UTF-8; bash -s"]),
                           input=script.replace("\r\n", "\n").encode("utf-8"), capture_output=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        die(f"ssh TIMEOUT tras {timeout}s (el canal no cerró; ¿algo en segundo plano sigue enganchado al "
            f"pipe?) — script:\n{script[:200]}")
    out = r.stdout.decode("utf-8", "replace").strip()
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode and check:
        die(f"ssh falló: {err or out}")
    return out if capture else (r.returncode == 0)


def ssh_ok():
    return subprocess.run(_ssh_cmd(["true"]), capture_output=True).returncode == 0


def scp_from(remote, local):
    r = subprocess.run(["scp", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-P", PORT,
                        f"{USER}@127.0.0.1:{remote}", local], capture_output=True)
    return r.returncode == 0


def scp_to(local, remote):
    r = subprocess.run(["scp", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-P", PORT,
                        local, f"{USER}@127.0.0.1:{remote}"], capture_output=True)
    return r.returncode == 0


# ---------------------------------------------------------------- ver
def shot(path=None):
    path = path or os.path.join(TMP, "vm.png")
    vbox("controlvm", VM, "screenshotpng", path)
    return path


def _tess_tsv(tess, png, scale=1.0, ox=0, oy=0):
    r = subprocess.run([tess, png, "-", "--psm", "11", "tsv"], capture_output=True, text=True, encoding="utf-8")
    out = []
    for ln in r.stdout.splitlines()[1:]:
        c = ln.split("\t")
        if len(c) >= 12 and c[0] == "5" and c[11].strip() and float(c[10]) >= 0:
            x, y, w, h = (int(float(c[i]) / scale) for i in (6, 7, 8, 9))
            out.append((c[11].strip(), x + ox, y + oy, w, h))
    return out


def _ocr_words(png, region=None, thorough=False):
    r"""Salida común: '<palabra>\t[x,y WxH]' en píxeles del invitado.
    region=(x,y,w,h) acelera (requiere Pillow). thorough=True añade una segunda pasada con la imagen
    ampliada x2 y en canal mínimo RGB, que lee el texto claro sobre botones de color ("Next", "I Accept") que la pasada
    normal no ve (medido: Tesseract no encontraba 'Next' blanco sobre naranja en Burp)."""
    ox = oy = 0
    rs = 1.0                       # factor de ampliación de la pasada normal (solo con región: Tesseract falla en franjas pequeñas)
    if region:
        try:
            from PIL import Image
            im = Image.open(png)
            ox, oy = int(region[0]), int(region[1])
            png = os.path.join(TMP, "_vmreg.png")
            cr = im.crop((ox, oy, ox + int(region[2]), oy + int(region[3])))
            rs = 3.0
            cr.resize((int(cr.width * rs), int(cr.height * rs)), Image.LANCZOS).save(png)
        except ImportError:
            ox = oy = 0
    ctrl = os.path.expanduser("~/Desktop/ctrl-kit/ocr")
    if os.environ.get("VM_OCR") != "tesseract" and not IS_WIN and os.access(ctrl, os.X_OK):
        return subprocess.run([ctrl, "--words", png], capture_output=True, text=True).stdout
    tess = find_tesseract()
    if not tess:
        die("falta Tesseract (Windows: winget install UB-Mannheim.TesseractOCR; ver PORTABILIDAD.md)")
    words = _tess_tsv(tess, png, rs, ox, oy)
    if thorough:
        try:
            from PIL import Image, ImageChops
            # Canal MÍNIMO de R,G,B: el blanco (255,255,255) se queda en 255 y un naranja/azul cae a su canal más
            # bajo, así el texto claro sobre botón de color gana contraste. (Probado: gris/invertido NO lo lee.)
            r, g, b = Image.open(png).convert("RGB").split()
            im = ImageChops.darker(ImageChops.darker(r, g), b)
            im = im.resize((int(im.width * 2 / rs), int(im.height * 2 / rs)), Image.LANCZOS)   # (png ya viene ×rs)
            alt = os.path.join(TMP, "_vminv.png")
            im.save(alt)
            for w in _tess_tsv(tess, alt, 2.0, ox, oy):
                if not any(w[0].lower() == o[0].lower() and abs(w[1] - o[1]) < 10 and abs(w[2] - o[2]) < 10 for o in words):
                    words.append(w)
        except ImportError:
            pass
    return "\n".join(f"{t}\t[{x},{y} {w}x{h}]" for t, x, y, w, h in words) + "\n"


def _words_text(png=None, region=None, thorough=False):
    return " ".join(l.split("\t")[0] for l in _ocr_words(png or shot(), region, thorough).splitlines() if "\t" in l).lower()


def focus(x, y, why="", w=None, h=None):
    """Dice a la EDICIÓN dónde está lo importante ahora (en píxeles del invitado). short_desde_toma.py
    encuadra el Short alrededor de este punto. waitfor lo registra solo (dónde apareció el texto).

    Con `w,h` (REGIÓN, p. ej. el rectángulo exacto de una ventana de terminal) la edición usa LETTERBOX de
    esa región completa — nunca recorta. SIN `w,h` (un punto suelto) usa un recorte centrado de tamaño fijo
    (816×961), que SÍ puede dejar fuera el borde de una ventana más ancha.

    REGLA: para cualquier terminal/texto que pueda ocupar TODO el ancho de su ventana, pasa SIEMPRE `w,h`
    (la geometría con la que la colocaste, p. ej. `place_id`) justo tras darle el foco y ANTES de teclear.
    El ratón no se mueve mientras se teclea, así que un `focus` sin región (basado en un punto fijo) no
    sabe que el texto puede llegar hasta el borde derecho — cortaba comandos largos (medido: sshole-run7,
    "22/tcp" salía como "cp" y "172.17.0.2" como "2.17.0.2"). Reserva el punto suelto para un énfasis
    puntual (un clic, un resultado corto) donde SÍ sabes que todo lo importante cabe en 816×961."""
    args = [int(x), int(y)]
    if w and h:
        args += [int(w), int(h)]
    _log(op="focus", args=args, why=why)


@logged("waitfor")
def waitfor(text, seg=20, region=None):
    t0 = time.time()
    want = text.lower()
    first = ocr_buscar.norm(want.split()[0]) if want.split() else ""
    while time.time() - t0 < seg:
        png = shot()
        for thorough in (False, True):
            lines = _ocr_words(png, region, thorough).splitlines(True)
            joined = " ".join(l.split("	")[0] for l in lines if "	" in l).lower()
            if want in joined:
                # dónde se vio el texto -> foco para el encuadre del Short
                for modo in ("exacta", "contiene"):
                    r = ocr_buscar.buscar(lines, first, 1, 1.0, region, "", modo) if len(first) >= 3 else None
                    if r:
                        x, y = (int(v) for v in r.split(","))
                        focus(x, y, f"waitfor:{text[:30]}")
                        break
                return True
        time.sleep(0.4)
    return False


def waitstill(seg=10, every=0.5, tol=0.002, top=40):
    """Espera a que la pantalla deje de cambiar. Compara dos capturas seguidas por FRACCIÓN de píxeles distintos
    (< tol) e ignora la franja superior (`top` px): el panel de Kali tiene un gráfico de CPU animado y el cursor de
    texto parpadea, y con una comparación exacta nunca se estabilizaba (medido). Sin Pillow/numpy cae a hash exacto."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        np = None
    t0, prev = time.time(), None
    while time.time() - t0 < seg:
        png = shot(os.path.join(TMP, "_still.png"))
        if np:
            cur = np.asarray(Image.open(png).convert("L"))[top:]
            if prev is not None and prev.shape == cur.shape and float((np.abs(cur.astype(int) - prev) > 24).mean()) < tol:
                return True
            prev = cur.astype(int)
        else:
            h = hashlib.md5(open(png, "rb").read()).hexdigest()
            if h == prev:
                return True
            prev = h
        time.sleep(every)
    return False


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


# ---------------------------------------------------------------- reproductor de planes (corre EN el invitado)
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


# ---------------------------------------------------------------- actuar
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


@logged("labcheck")
def labcheck(needle, seg=10):
    """Verificación SIN OCR: el lab imprime una línea por petición en /tmp/lab.log."""
    t0 = time.time()
    while time.time() - t0 < seg:
        if needle in ssh("cat /tmp/lab.log 2>/dev/null", capture=True, check=False):
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------- apps y ventanas
def launch_terminal(title, wclass="qterminal"):
    """Abre un terminal NUEVO y devuelve su ID de ventana (estable). El TÍTULO se renombra a mano con
    `xdotool set_window`: el prompt de Kali no lo toca después, así sigue sirviendo para distinguir
    ventanas en pantalla, pero el CONTROL (activate/move) debe ir siempre por ID, no por título, porque
    dos terminales comparten el mismo título por defecto ("usuario@host: ~") y _wid() cogería cualquiera."""
    before = set(ssh(f"xdotool search --class {wclass}", capture=True, check=False).split())
    launch("qterminal")
    t0 = time.time()
    wid = None
    while time.time() - t0 < 6:
        after = set(ssh(f"xdotool search --class {wclass}", capture=True, check=False).split())
        new = after - before
        if new:
            wid = new.pop()
            break
        time.sleep(0.3)
    if not wid:
        die(f"no se abrió el terminal (título previsto: {title})")
    ssh(f"xdotool set_window --name {shlex.quote(title)} {wid}")
    return wid


def place_id(wid, x, y, w, h):
    """Como place() pero por ID de ventana directamente (sin buscar por título)."""
    ssh(f"xdotool windowmove {wid} {x} {y}; xdotool windowsize {wid} {w} {h}")


def activate_id(wid):
    ssh(f"xdotool windowactivate {wid}")
    time.sleep(0.4)


def type_in(wid, text, wpm=45.0, typos=0.015, seed=None):
    """type_human pero exigiendo foco por ID de ventana (no por título: ver launch_terminal)."""
    cur = ssh("xdotool getactivewindow 2>/dev/null", capture=True, check=False)
    if cur != str(wid):
        die(f"FOCO INCORRECTO: ventana activa {cur} (esperada {wid}) — NO escribo")
    play(tipear.plan(text, wpm, typos, random.Random(seed)))


def launch(cmd):
    ssh(f"nohup {cmd} >/dev/null 2>&1 &")


def _wid(title):
    return ssh(f'xdotool search --onlyvisible --name {shlex.quote(title)} | head -1', capture=True, check=False)


@logged("activate")
def activate(title, seg=8):
    t0 = time.time()
    while time.time() - t0 < seg:
        w = _wid(title)
        if w:
            ssh(f"xdotool windowactivate {w}")
            time.sleep(0.4)
            if title.lower() in active_title().lower():
                return True
        time.sleep(0.5)
    die(f"no pude dar foco a una ventana '{title}' (activa: '{active_title()}')")


def maximize(title):
    """Maximiza a la pantalla REAL del invitado (no un tamaño fijo): wmctrl respeta panel y decoraciones."""
    wid = _wid(title)
    if wid:
        ssh(f"wmctrl -ir {wid} -b remove,maximized_vert,maximized_horz; wmctrl -ir {wid} -b add,maximized_vert,maximized_horz",
            check=False)
    return bool(wid)


def place(title, x, y, w, h):
    wid = _wid(title)
    if not wid:
        die(f"no hay ventana visible '{title}'")
    ssh(f"xdotool windowmove {wid} {x} {y}; xdotool windowsize {wid} {w} {h}")
    time.sleep(0.5)
    g = dict(l.split("=") for l in ssh(f"xdotool getwindowgeometry --shell {wid}", capture=True).splitlines())
    got = [int(g[k]) for k in ("X", "Y", "WIDTH", "HEIGHT")]
    if abs(got[2] - w) > 12 or abs(got[3] - h) > 40:
        die(f"geometría real {got} != pedida {[x, y, w, h]}")
    return got


# ---------------------------------------------------------------- ciclo de vida
def vm_state():
    for l in vbox("showvminfo", VM, "--machinereadable", check=False).stdout.splitlines():
        if l.startswith("VMState="):
            return l.split('"')[1]
    return "desconocido"


def ensure_natpf():
    """Garantiza el reenvío 127.0.0.1:PORT -> 22 (solo se puede añadir con la VM APAGADA)."""
    info = vbox("showvminfo", VM, "--machinereadable", check=False).stdout
    if f",{PORT}," in info and "Forwarding" in info:
        return True
    if vm_state() not in ("poweroff", "aborted", "saved"):
        return False
    vbox("modifyvm", VM, "--natpf1", f"ssh,tcp,127.0.0.1,{PORT},,22")
    return True


def start(seg=150):
    if vm_state() in ("poweroff", "aborted"):
        ensure_natpf()
    if vm_state() != "running":
        vbox("startvm", VM, "--type", "gui")
    t0 = time.time()
    while time.time() - t0 < seg:
        if ssh_ok():
            return True
        time.sleep(3)
    return False


def stop(seg=90):
    vbox("controlvm", VM, "acpipowerbutton", check=False)
    t0 = time.time()
    while time.time() - t0 < seg:
        if vm_state() == "poweroff":
            return True
        time.sleep(2)
    return False


def suspend():
    """Guarda el estado de la VM con todo abierto (NO es un snapshot ni una copia: reanuda y desaparece)."""
    vbox("controlvm", VM, "savestate")
    return vm_state() == "saved"


def resume(seg=60):
    t0 = time.time()
    ok = start(seg)
    return ok, round(time.time() - t0, 1)


def set_res(w, h):
    vbox("controlvm", VM, "setvideomodehint", str(w), str(h), "32")


# ---------------------------------------------------------------- toma: registro + grabación + mapa de edición
def take_start(name):
    d = os.path.join(REPO, "editor", "crudo")
    os.makedirs(d, exist_ok=True)
    log = os.path.join(d, f"{name}.steps.jsonl")
    open(log, "w", encoding="utf-8").close()
    _save_state({"name": name, "log": log})
    _log(op="take_start", name=name)
    print("registro:", log)


def mark(label):
    _log(op="mark", label=label)


def find_ffmpeg():
    """ffmpeg del ANFITRIÓN: PATH, o la ruta de winget en Windows (el PATH no se refresca en terminales ya abiertas)."""
    c = shutil.which("ffmpeg")
    if c:
        return c
    for g in glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*",
                                    "ffmpeg-*", "bin", "ffmpeg.exe")):
        return g
    return None


def _crudo(name, ext):
    return os.path.join(REPO, "editor", "crudo", f"{name}.{ext}")


def rec_start(w=None, h=None, fps=30, guest=False):
    """Empieza a grabar. POR DEFECTO con la grabación NATIVA de VirtualBox, en el ANFITRIÓN: no instala ni
    ejecuta nada dentro de la VM, funciona sin SSH y el cursor del invitado sale en el vídeo (medido).
    `guest=True` usa ffmpeg x11grab dentro del invitado (necesita SSH+ffmpeg): solo como alternativa.

    VirtualBox NO deja cambiar la resolución NI el nombre de fichero de la grabación una vez que
    `recording_enabled` ha estado "on" en esta sesión de la VM — ni siquiera tras `recording off`
    (medido: sigue dando E_INVALIDARG "Cannot change ... while recording is enabled"; `modifyvm` lo
    arreglaría pero exige la VM apagada, imposible entre tomas). Por eso: se configura resolución/fichero
    SOLO la primera vez que `rec_screen_dest_filename` está vacío; las siguientes tomas REUTILIZAN ese
    mismo fichero fijo (`_vbox_rec.webm`) y solo hacen `start`/`stop` — sin tocar más ajustes."""
    st = _state()
    if not st.get("name"):
        die("primero: take start NOMBRE")
    if guest:
        return _rec_start_guest(st, w, h, fps)
    if not w:
        m = ssh("xdpyinfo | grep dimensions | awk '{print $2}'", capture=True, check=False) if ssh_ok() else ""
        w, h = (int(v) for v in m.split("x")) if "x" in m else (1920, 1012)
    info = vbox("showvminfo", VM, "--machinereadable", check=False).stdout
    cur_file = re.search(r'rec_screen_dest_filename="([^"]*)"', info)
    fixed = _crudo("_vbox_rec", "webm")
    if not cur_file or not cur_file.group(1):
        # primera vez: configurar de verdad (aquí SÍ se puede, antes de que nada quede "enabled")
        for args in (["videores", str(w), str(h)], ["videofps", str(fps)], ["videorate", "10000"],
                    ["filename", fixed]):
            r = vbox("controlvm", VM, "recording", *args, check=False)
            if r.returncode:
                die(f"VBoxManage recording {args[0]} falló: {r.stderr.strip()[:150]}")
    elif cur_file.group(1) != fixed:
        print(f"aviso: VirtualBox ya tenía fijado otro fichero de grabación ({cur_file.group(1)}); "
              "se reutiliza tal cual (no se puede cambiar en caliente)")
        fixed = cur_file.group(1)
    if os.path.exists(fixed):
        os.remove(fixed)                       # que la toma anterior no deje restos en el fichero fijo
    vbox("controlvm", VM, "recording", "start", check=False)
    time.sleep(0.8)
    if 'recording_started="on"' not in vbox("showvminfo", VM, "--machinereadable", check=False).stdout:
        die("la grabación de VirtualBox no arrancó")
    st.update(rec_t0=time.time(), rec_backend="vbox", rec_file=fixed)
    _save_state(st)
    _log(op="rec_start", backend="vbox", size=f"{w}x{h}", fps=fps)
    print(f"grabando (VirtualBox, anfitrión) {w}x{h}@{fps} -> {fixed}")


def _rec_start_guest(st, w, h, fps):
    if not w:
        m = ssh("xdpyinfo | grep dimensions | awk '{print $2}'", capture=True)
        w, h = (int(v) for v in m.split("x"))
    # setsid, no nohup+disown: con disown el canal SSH tarda MINUTOS en devolver el control aunque el
    # proceso quede bien lanzado (medido); setsid lo desengancha de la sesión y ssh() vuelve al instante.
    ssh(f"rm -f /tmp/cutly_rec.mp4; setsid ffmpeg -y -f x11grab -draw_mouse 1 -framerate {fps} "
        f"-video_size {w}x{h} -i :0 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p "
        f"-movflags +faststart /tmp/cutly_rec.mp4 </dev/null >/tmp/cutly_rec.log 2>&1 &")
    for _ in range(20):
        if ssh("pgrep -x ffmpeg >/dev/null && test -s /tmp/cutly_rec.mp4 && echo ok", capture=True, check=False) == "ok":
            break
        time.sleep(0.3)
    else:
        die("ffmpeg no arrancó en el invitado (¿instalado? sudo apt install ffmpeg). Log: /tmp/cutly_rec.log")
    st.update(rec_t0=time.time(), rec_backend="guest")
    _save_state(st)
    _log(op="rec_start", backend="guest", size=f"{w}x{h}", fps=fps)
    print(f"grabando (ffmpeg DENTRO de la VM) {w}x{h}@{fps}")


def rec_stop():
    """Para la grabación y deja editor/crudo/<toma>.mp4 (H.264, 30 fps constantes: lo que espera la Fase 2)."""
    st = _state()
    _log(op="rec_stop")
    dest = _crudo(st.get("name", "toma"), "mp4")
    if st.get("rec_backend") == "guest":
        ssh("pkill -INT -x ffmpeg; for i in $(seq 1 30); do pgrep -x ffmpeg >/dev/null || break; sleep 0.3; done", check=False)
        if not scp_from("/tmp/cutly_rec.mp4", dest):
            die("no pude traer el vídeo (scp). Sigue en el invitado: /tmp/cutly_rec.mp4")
    else:
        vbox("controlvm", VM, "recording", "stop", check=False)
        time.sleep(2)                                   # VirtualBox cierra el .webm unos instantes después
        # Fichero FIJO (ver rec_start: VBox no deja cambiar el nombre tras la 1ª vez), no uno con el
        # nombre de la toma: VirtualBox lo guarda como "<fijo>-screen0.webm" (sufijo de pantalla).
        fixed = st.get("rec_file") or _crudo("_vbox_rec", "webm")
        webms = sorted(glob.glob(fixed.replace(".webm", "") + "*.webm"))
        if not webms:
            die(f"VirtualBox no dejó el .webm de la grabación (esperado junto a {fixed})")
        ff = find_ffmpeg()
        if not ff:
            die("falta ffmpeg en el anfitrión (Windows: winget install Gyan.FFmpeg)")
        # VP8 de VirtualBox -> H.264 CFR 30 fps: calidad alta y compatible con construir_short/construir_clip
        r = subprocess.run([ff, "-v", "error", "-y", "-i", webms[0], "-c:v", "libx264", "-preset", "medium", "-crf", "14",
                            "-r", "30", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", dest],
                           capture_output=True, text=True)
        if r.returncode:
            die(f"ffmpeg no pudo convertir la grabación: {r.stderr.strip()[:200]}")
        for f in webms:
            os.remove(f)
    st.pop("rec_t0", None)
    _save_state(st)
    print("vídeo:", dest)
    return dest


def take_end():
    st = _state()
    if st.get("rec_t0"):
        rec_stop()
    if st.get("log"):
        _log(op="take_end")
        print("mapa:", build_map(st["name"]))
    _save_state({})


def build_map(name):
    """Mapa de edición (doc 04 §Fase 4) generado desde el registro: un bloque por 'mark' con su rango en el vídeo."""
    log = os.path.join(REPO, "editor", "crudo", f"{name}.steps.jsonl")
    ev = [json.loads(l) for l in open(log, encoding="utf-8") if l.strip()]
    t_of = lambda e: e.get("t_video", e["t_wall"] - ev[0]["t_wall"])
    marks = [e for e in ev if e["op"] == "mark"]
    end = t_of(ev[-1])
    rows = ["| # | Momento | Desde (s) | Hasta (s) | Dura | Pasos |", "|---|---|---|---|---|---|"]
    for i, m in enumerate(marks):
        a = t_of(m)
        b = t_of(marks[i + 1]) if i + 1 < len(marks) else end
        n = sum(1 for e in ev if e["op"] not in ("mark", "take_start", "take_end", "rec_start", "rec_stop") and a <= t_of(e) < b)
        rows.append(f"| {i + 1} | {m['label']} | {a:.1f} | {b:.1f} | {b - a:.1f} s | {n} |")
    fails = [e for e in ev if e.get("ok") is False]
    out = f"# Mapa de edición — {name}\n\n" + "\n".join(rows) + "\n"
    if fails:
        out += "\n## Pasos fallidos (rehacer)\n" + "\n".join(f"- t={t_of(e):.1f}s `{e['op']}` {e.get('error', '')}" for e in fails) + "\n"
    out += "\nTiempos en segundos desde el inicio del vídeo (±0,3 s). Úsalos en editor/CLAUDE.md para los cortes.\n"
    path = os.path.join(REPO, "editor", "crudo", f"{name}.mapa.md")
    open(path, "w", encoding="utf-8").write(out)
    return path


# ---------------------------------------------------------------- estado de partida
def _is_running(pattern):
    return ssh(f"pgrep -f {shlex.quote(pattern)} >/dev/null && echo si || echo no", capture=True) == "si"


def burp_up(seg=120):
    """Burp Community listo en el Dashboard. Los diálogos de arranque salen EN CADA arranque (clic verificado
    por OCR: Enter NO funciona en Swing). Con `suspend`/`resume` se evita todo esto entre tomas."""
    if _is_running("burpsuite.jar") and _wid("Temporary Project"):
        return True
    if not _is_running("burpsuite.jar"):
        launch("burpsuite")
    t0 = time.time()
    while time.time() - t0 < seg:
        for t in ("Delete old temporary", "Burp Suite Community"):
            w = _wid(t)
            if w:
                ssh(f"xdotool windowactivate {w}")
                time.sleep(0.4)
                break
        words = _words_text()
        if "delete old temporary" in words:          # el modal primero: el OCR sigue viendo lo de debajo
            clicktext("Delete", -1)
            time.sleep(1.5)
            continue
        if "temporary project" in words:
            break
        time.sleep(1)
    else:
        die("Burp no mostró el diálogo de proyecto (¿EULA sin aceptar? ver 00-empezar-aqui-vm.md §2)")
    clicktext("Next")
    if not waitfor("Use Burp defaults", 20):
        die("el clic en Next no avanzó")
    clicktext("Start")
    for _ in range(40):
        if _wid("Temporary Project"):
            return True
        time.sleep(1.5)
    die("Burp no llegó a la ventana principal")


# Modales conocidos: (texto que lo identifica, [textos a pulsar en orden]). Se cierran con clic VERIFICADO
# (comprobando después que el texto ya no está): Enter no activa los botones Swing de Burp.
MODALES = [
    ("burp suite is out of date", ["Don't", "OK"]),
    ("delete old temporary", ["Delete"]),
]


def waitgone(text, seg=6):
    t0 = time.time()
    while time.time() - t0 < seg:
        if text.lower() not in _words_text():
            return True
        time.sleep(0.5)
    return False


@logged("dismiss")
def dismiss_modals(rounds=4):
    """Cierra los modales conocidos que haya en pantalla. Devuelve cuántos cerró."""
    n = 0
    for _ in range(rounds):
        words = _words_text()
        hit = next(((t, b) for t, b in MODALES if t in words), None)
        if not hit:
            return n
        for btn in hit[1]:
            clicktext(btn, -1 if btn == "OK" else 1)
            time.sleep(0.4)
        if not waitgone(hit[0]):
            die(f"el modal '{hit[0]}' no se cerró tras pulsar {hit[1]}")
        n += 1
    return n


def prepare(cold=False):
    """Estado de partida: lab, Burp en el Dashboard y Firefox 'demo'. Intenta reanudar el estado guardado."""
    if vm_state() == "saved" and not cold:
        ok, s = resume()
        print(f"reanudado en {s}s" if ok else "no reanudó")
    if not ssh_ok():
        die("la VM no responde por SSH (vm_control.py start)")
    if not _is_running("lab_idor.py"):
        ssh("setsid python3 ~/lab/lab_idor.py </dev/null >/tmp/lab.log 2>&1 &")  # setsid: no cuelga el canal SSH (doc 09)
        time.sleep(1)
    burp_up()
    if not _is_running("firefox.*-P demo"):
        launch("firefox --no-remote -P demo")
        for _ in range(20):
            if _wid("Mozilla Firefox"):
                break
            time.sleep(1)
    time.sleep(2)               # los avisos de Burp (p. ej. "out of date") salen unos segundos DESPUÉS de abrir
    dismiss_modals()
    for title in ("Temporary Project", "Mozilla Firefox"):
        maximize(title)
    activate("Mozilla Firefox")
    faltan = [t for t in ("Temporary Project", "Mozilla Firefox") if not _wid(t)]
    if faltan or "usuarioA" not in ssh('curl -s "http://127.0.0.1:8765/cuenta?id=1001"', capture=True, check=False):
        die(f"prepare INCOMPLETO: faltan {faltan or 'el lab'}")
    print("prepare OK. Tip: `vm_control.py suspend` guarda este estado para reanudar en segundos.")


def bootstrap():
    """Deja la VM controlable: regla NAT + clave SSH dedicada. Idempotente. NO adivina contraseñas."""
    if not os.path.exists(KEY):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "cutly-vm", "-f", KEY], check=True)
        print(f"clave dedicada creada: {KEY}")
    if vm_state() in ("poweroff", "aborted"):
        print("regla NAT ssh:", "ok" if ensure_natpf() else "no se pudo")
    if vm_state() != "running":
        vbox("startvm", VM, "--type", "gui")
        print("VM arrancando; espera a ver el escritorio e inicia sesión (la sesión la pones tú)")
        time.sleep(40)
    if ssh_ok():
        print("ya está configurada (SSH con la clave dedicada funciona)")
        return
    pub = open(KEY + ".pub").read().strip()
    gp = os.environ.get("VM_GUEST_PASS")
    if gp:   # Camino 1 (preferido): guestcontrol con la contraseña que TÚ das en VM_GUEST_PASS
        r = vbox("guestcontrol", VM, "run", "--username", USER, "--password", gp, "--exe", "/bin/bash", "--",
                 "bash", "-c", f"mkdir -p ~/.ssh && echo '{pub}' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && "
                 "chmod 600 ~/.ssh/authorized_keys && (sudo -n systemctl enable --now ssh 2>/dev/null || true)", check=False)
        print("guestcontrol:", "ok" if r.returncode == 0 else r.stderr.strip()[:200])
    else:    # Camino 2: teclear en un terminal del invitado con el teclado en US (solo letras)
        k = lambda *a: vbox("controlvm", VM, "keyboardputscancode", *a)
        enter = lambda: (k("1c", "9c"), time.sleep(0.8))
        print("abriendo un terminal en el invitado (Ctrl+Alt+T) y escribiendo la clave...")
        k("1d", "38", "14", "94", "b8", "9d")
        time.sleep(3)
        for line in ("setxkbmap us", "mkdir -p ~/.ssh", f"echo '{pub}' >> ~/.ssh/authorized_keys",
                     "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"):
            vbox("controlvm", VM, "keyboardputstring", line)
            enter()
    time.sleep(1)
    print("OK: SSH operativo" if ssh_ok() else "FALLÓ: revisa la captura (shot), que sshd esté activo y la regla NAT")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)

    def opt(n, d=None, c=str):
        if n not in a:
            return d
        if a.index(n) + 1 >= len(a):
            die(f"falta el valor de {n}")
        return c(a[a.index(n) + 1])

    cmd = a[0]
    if cmd == "start":
        ok = start()
        print("OK" if ok else "TIMEOUT: la VM no respondió por SSH")
        sys.exit(0 if ok else 1)
    elif cmd == "stop":
        print("apagada" if stop() else "no se apagó a tiempo (se dejó como está)")
    elif cmd == "suspend":
        print("estado guardado" if suspend() else "no se pudo guardar")
    elif cmd == "resume":
        ok, s = resume()
        print(f"{'OK' if ok else 'TIMEOUT'} en {s}s")
        sys.exit(0 if ok else 1)
    elif cmd == "res":
        set_res(int(a[1]), int(a[2]))
    elif cmd == "status":
        print(f"VM {VM}: {vm_state()} | ssh: {'sí' if ssh_ok() else 'no'}")
        if ssh_ok():
            print("pantalla:", ssh("xrandr | grep '\\*' | head -1", capture=True))
            print("ventana activa:", active_title())
    elif cmd == "bootstrap":
        bootstrap()
    elif cmd == "prepare":
        prepare("--cold" in a)
    elif cmd == "take":
        {"start": lambda: take_start(a[2]), "end": take_end}[a[1]]()
    elif cmd == "mark":
        mark(a[1])
    elif cmd == "rec":
        if a[1] == "start":
            nums = [x for x in a[2:] if x.isdigit()]
            rec_start(int(nums[0]) if len(nums) > 0 else None, int(nums[1]) if len(nums) > 1 else None,
                      int(nums[2]) if len(nums) > 2 else 30, guest="--guest" in a)
        else:
            rec_stop()
    elif cmd == "mapa":
        print(build_map(a[1]))
    elif cmd == "shot":
        print(shot(a[1] if len(a) > 1 else None))
    elif cmd == "pos":
        print("%d,%d" % pos(fresh=True))
    elif cmd == "move":
        move(int(a[1]), int(a[2]), opt("--dur", None, float), opt("--seed", None, int))
    elif cmd == "click":
        click("dc" in a)
    elif cmd == "type":
        type_human(a[1], opt("--wpm", 55.0, float), opt("--typos", 0.015, float), opt("--seed", None, int), opt("--in"))
    elif cmd == "typeurl":
        typeurl(a[1], opt("--wpm", 45.0, float), opt("--in"))
    elif cmd == "key":
        ssh("xdotool key " + " ".join(shlex.quote(k) for k in a[1:]))
        _log(op="key", args=a[1:])
    elif cmd == "windows":
        print(ssh('for w in $(xdotool search --onlyvisible --name ""); do '
                  'n=$(xdotool getwindowname $w 2>/dev/null); [ -n "$n" ] && '
                  'echo "$w | $n | $(xdotool getwindowgeometry --shell $w | tr "\\n" " ")"; done; true', capture=True))
    elif cmd == "waitfor":
        reg = tuple(float(v) for v in opt("--region").split(",")) if "--region" in a else None
        seg = float(a[2]) if len(a) > 2 and not a[2].startswith("--") else 20
        ok = waitfor(a[1], seg, region=reg)
        print("OK" if ok else "TIMEOUT")
        sys.exit(0 if ok else 1)
    elif cmd == "dismiss":
        print("cerrados:", dismiss_modals())
    elif cmd == "focus":
        # focus X Y [W H] [motivo]  — W H opcionales (región, letterbox sin recortar); motivo es lo que sobre
        wh = a[3:5] if len(a) > 4 and a[3].isdigit() and a[4].isdigit() else None
        resto = a[5:] if wh else a[3:]
        focus(int(a[1]), int(a[2]), " ".join(resto), *(int(v) for v in wh) if wh else (None, None))
    elif cmd == "waitstill":
        ok = waitstill(float(a[1]) if len(a) > 1 else 10)
        print("OK" if ok else "TIMEOUT")
        sys.exit(0 if ok else 1)
    elif cmd == "labcheck":
        ok = labcheck(a[1], float(a[2]) if len(a) > 2 else 10)
        print("OK" if ok else "NO VISTO")
        sys.exit(0 if ok else 1)
    elif cmd == "clicktext":
        n = int(a[2]) if len(a) > 2 and a[2].lstrip('-').isdigit() else 1
        reg = tuple(float(v) for v in opt("--region").split(",")) if "--region" in a else None
        print("%d,%d" % clicktext(a[1], n, "dc" in a, opt("--sub", ""), reg=reg))
    elif cmd == "clickimg":
        print("%d,%d" % clickimg(a[1], "dc" in a))
    elif cmd == "selecttext":
        n = int(a[2]) if len(a) > 2 and a[2].lstrip('-').isdigit() else 1
        selecttext(a[1], n, opt("--sub", ""))
        print("OK")
    elif cmd == "launch":
        launch(a[1])
    elif cmd == "activate":
        activate(a[1])
        print("OK")
    elif cmd == "place":
        print(place(a[1], int(a[2]), int(a[3]), int(a[4]), int(a[5])))
    elif cmd == "put":
        print("OK" if scp_to(a[1], a[2]) else "FALLÓ")
    elif cmd == "get":
        print("OK" if scp_from(a[1], a[2]) else "FALLÓ")
    elif cmd == "run":
        print(ssh(a[1], capture=True))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
