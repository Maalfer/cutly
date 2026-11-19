"""Apps y ventanas del invitado: lanzar, dar foco, colocar. El control va por ID de ventana (estable), no por título."""
import shlex
import time

from .config import die
from .conexion import ssh
from .entrada import active_title
from .registro import logged


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


# Maximizar como lo hace wmctrl por dentro: un mensaje EWMH _NET_WM_STATE al gestor de ventanas, enviado con python3
# + ctypes sobre libX11 (los dos vienen en Kali; wmctrl no, y su xdotool 3.2016 no tiene `windowstate`: medido).
# Alternativas descartadas (medido): colocar la ventana en _NET_WORKAREA no descuenta la barra de título y la
# ventana se sale por abajo; `key super+Up` depende de los atajos del escritorio.
MAXIMIZAR_EWMH = r'''
import ctypes, sys
x = ctypes.cdll.LoadLibrary("libX11.so.6")
x.XOpenDisplay.restype = ctypes.c_void_p
x.XInternAtom.restype = ctypes.c_ulong
x.XDefaultRootWindow.restype = ctypes.c_ulong
d = ctypes.c_void_p(x.XOpenDisplay(None))
if not d.value:
    sys.exit("sin DISPLAY")
atom = lambda n: x.XInternAtom(d, n.encode(), False)
class Ev(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                ("format", ctypes.c_int), ("l", ctypes.c_long * 5), ("pad", ctypes.c_long * 12)]
def estado(accion):   # 0 quitar, 1 poner
    e = Ev(type=33, send_event=1, window=int(sys.argv[1]), message_type=atom("_NET_WM_STATE"), format=32)
    e.l[0], e.l[1], e.l[2], e.l[3] = accion, atom("_NET_WM_STATE_MAXIMIZED_VERT"), atom("_NET_WM_STATE_MAXIMIZED_HORZ"), 1
    x.XSendEvent(d, ctypes.c_ulong(x.XDefaultRootWindow(d)), False, (1 << 20) | (1 << 19), ctypes.byref(e))
    x.XFlush(d)
estado(0); estado(1)
'''


def maximize(title):
    """Maximiza a la pantalla REAL del invitado (no un tamaño fijo), respetando panel y decoraciones: con wmctrl si
    está; si no, con el mismo mensaje EWMH que usa wmctrl (MAXIMIZAR_EWMH)."""
    wid = _wid(title)
    if wid:
        ssh(f"if command -v wmctrl >/dev/null; then "
            f"wmctrl -ir {wid} -b remove,maximized_vert,maximized_horz; wmctrl -ir {wid} -b add,maximized_vert,maximized_horz; "
            f"else python3 -c {shlex.quote(MAXIMIZAR_EWMH)} {wid}; fi", check=False)
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


def _is_running(pattern):
    return ssh(f"pgrep -f {shlex.quote(pattern)} >/dev/null && echo si || echo no", capture=True) == "si"
