"""Estado de partida de las demos (lab + Burp + Firefox) y verificación sin OCR contra el log del lab."""
import time

from .config import die
from .conexion import ssh, ssh_ok
from .entrada import clicktext
from .maquina import resume, vm_state
from .pantalla import _words_text, waitfor, waitgone
from .registro import logged
from .ventanas import _is_running, _wid, activate, launch, maximize


@logged("labcheck")
def labcheck(needle, seg=10):
    """Verificación SIN OCR: el lab imprime una línea por petición en /tmp/lab.log."""
    t0 = time.time()
    while time.time() - t0 < seg:
        if needle in ssh("cat /tmp/lab.log 2>/dev/null", capture=True, check=False):
            return True
        time.sleep(0.5)
    return False


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
        die("el invitado no responde por ningún canal (vm_control.py start; canal: VM_CANAL)")
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
