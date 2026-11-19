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


def _is_running(pattern):
    return ssh(f"pgrep -f {shlex.quote(pattern)} >/dev/null && echo si || echo no", capture=True) == "si"
