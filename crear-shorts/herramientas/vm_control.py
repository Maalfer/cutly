#!/usr/bin/env python3
"""
vm_control.py — Controla una VM Linux (X11) de VirtualBox con entrada HUMANA, desde el anfitrión.

ESTÁNDAR DEL REPO: todas las tomas para shorts se hacen DENTRO de una VM (ver METODOLOGIA/00-empezar-aqui-vm.md).
Este script es la "mano" de la IA: ve (capturas de VBoxManage), actúa (xdotool por SSH) y verifica (OCR).

Reutiliza el MISMO plan de pulsaciones y trayectos que en macOS (tipear.plan, mover.trayecto); solo
cambia el emisor. Funciona desde cualquier anfitrión con `VBoxManage`, `ssh`, `python3` y un OCR
(Vision de macOS vía ctrl-kit, o Tesseract en cualquier SO).

Por qué xdotool dentro del invitado y no VBoxManage (medido, doc 08): `controlvm keyboardputstring`
asume teclado US y CORROMPE el texto con otra distribución; VBoxManage NO tiene comando de ratón.

Requisitos en el invitado: Guest Additions, sshd, `xdotool`, sesión X11, una clave SSH autorizada.
Primera vez:  vm_control.py bootstrap     (deja todo listo; es idempotente)

Variables:  VM_NAME (def. kali)  VM_KEY (def. ~/.ssh/cutly_vm)  VM_SSH_PORT (def. 2222)  VM_USER (def. kali)
            VM_OCR=tesseract fuerza Tesseract (por defecto Vision si existe ~/Desktop/ctrl-kit/ocr)

CICLO DE VIDA
  start | stop | status | bootstrap
VER
  shot [salida.png]                     captura de la pantalla del invitado (~0,08 s)
  waitfor "texto" [seg]                 espera (OCR) a que aparezca un texto; código 1 si TIMEOUT
  windows                               ventanas visibles con geometría
  pos                                   posición del cursor del invitado
ACTUAR (todo con ritmo humano)
  move X Y [--dur S] [--seed N]         mueve con trayecto curvo
  click [dc]                            clic (dc = doble) en la posición actual
  clicktext PALABRA [n] [dc] [--sub TROZO]   mueve y clica una palabra de la pantalla (reintenta unos segundos)
  selecttext PALABRA [n] --sub TROZO    doble clic + COPIAR + comprobar + reintentar (ver doc 07 nº 34)
  type "texto" [--wpm 55] [--typos 0.015] [--seed N] [--in "Título"]
  typeurl URL [--wpm 45] [--in "Título"]    Ctrl+L, teclea, Suprimir (quita autocompletado), Enter
  key Return | ctrl+alt+t ...           pulsaciones sueltas (sintaxis xdotool)
ESTADO DE PARTIDA DE UNA TOMA
  prepare                               deja la VM lista (lab + Burp + Firefox demo, maximizados); idempotente
APPS Y VENTANAS
  launch "comando"                      lanza una app gráfica en el invitado (en segundo plano)
  activate "Título"                     da foco a una ventana y VERIFICA que lo tiene
  place "Título" X Y W H                coloca una ventana y verifica la geometría real
  run "comando"                         ejecuta un comando en el invitado (DISPLAY=:0, UTF-8)

`--in "Título"` es la GUARDA DE FOCO: si la ventana activa no contiene ese título, NO escribe (el texto va
siempre a la ventana con foco; lección del anfitrión, doc 07 nº 7).
"""
import os
import random
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tipear   # plan() de pulsaciones humanas
import mover    # trayecto() de ratón humano

VM = os.environ.get("VM_NAME", "kali")
KEY = os.environ.get("VM_KEY", os.path.expanduser("~/.ssh/cutly_vm"))
PORT = os.environ.get("VM_SSH_PORT", "2222")
USER = os.environ.get("VM_USER", "kali")
HERE = os.path.dirname(os.path.abspath(__file__))
TMP = os.environ.get("TMPDIR", "/tmp")


def die(msg):
    sys.exit(f"[vm_control] {msg}")


def _ssh_cmd(extra=None):
    return ["ssh", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new", "-p", PORT, f"{USER}@127.0.0.1"] + (extra or [])


def ssh(script, capture=False, check=True):
    # LC_ALL=C.UTF-8 es IMPRESCINDIBLE: sin locale UTF-8, xdotool descarta los caracteres no ASCII
    # ("Invalid multi-byte sequence") y desaparecen las tildes, ñ, € y ¿ (error real medido).
    r = subprocess.run(_ssh_cmd(["export DISPLAY=:0 LC_ALL=C.UTF-8 LANG=C.UTF-8; bash -s"]),
                       input=script, text=True, capture_output=True)
    if r.returncode and check:
        die(f"ssh falló: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip() if capture else (r.returncode == 0)


def ssh_ok():
    r = subprocess.run(_ssh_cmd(["true"]), capture_output=True, text=True)
    return r.returncode == 0


# ---------------------------------------------------------------- ver
def shot(path=None):
    path = path or os.path.join(TMP, "vm.png")
    subprocess.run(["VBoxManage", "controlvm", VM, "screenshotpng", path], check=True, capture_output=True)
    return path


def _ocr_words(png):
    """Salida común: '<palabra>\\t[x,y WxH]' en píxeles del invitado (escala 1)."""
    ctrl = os.path.join(os.path.expanduser("~/Desktop/ctrl-kit"), "ocr")
    if os.environ.get("VM_OCR") != "tesseract" and os.access(ctrl, os.X_OK):
        return subprocess.run([ctrl, "--words", png], capture_output=True, text=True).stdout
    # Tesseract (macOS/Linux/Windows): TSV nivel 5 = palabra
    r = subprocess.run(["tesseract", png, "-", "--psm", "11", "tsv"], capture_output=True, text=True)
    out = []
    for ln in r.stdout.splitlines()[1:]:
        c = ln.split("\t")
        if len(c) >= 12 and c[0] == "5" and c[11].strip() and float(c[10]) >= 0:
            out.append(f"{c[11].strip()}\t[{c[6]},{c[7]} {c[8]}x{c[9]}]")
    return "\n".join(out) + "\n"


def waitfor(text, seg=20):
    t0 = time.time()
    want = text.lower()
    while time.time() - t0 < seg:
        words = [l.split("\t")[0] for l in _ocr_words(shot()).splitlines() if "\t" in l]
        if want in " ".join(words).lower():
            return True
        time.sleep(0.6)
    return False


def pos():
    out = ssh("xdotool getmouselocation --shell", capture=True)
    d = dict(l.split("=") for l in out.splitlines() if "=" in l)
    return int(d["X"]), int(d["Y"])


def active_title():
    return ssh("xdotool getactivewindow getwindowname 2>/dev/null", capture=True, check=False)


def require_focus(title):
    if title and title.lower() not in active_title().lower():
        die(f"FOCO INCORRECTO: '{active_title()}' (esperado '{title}') — NO escribo")


# ---------------------------------------------------------------- actuar
def plan_to_script(plan):
    """Convierte un plan (k/bs/ret/tab/d/m) en un script bash con xdotool y esperas."""
    L = []
    for e in plan:
        if e[0] == "k":
            # Un carácter no ASCII exige que xdotool reasigne una tecla; si el proceso termina sin esperar,
            # restaura el teclado ANTES de que la app lea la tecla y el carácter se pierde (medido: con
            # --delay 0 fallaba siempre, con >= 30 ms acierta). Solo hace falta para no ASCII.
            d = 0 if ord(e[1]) < 128 else 40
            L.append(f"xdotool type --delay {d} -- {shlex.quote(e[1])}")
        elif e[0] == "bs":
            L.append("xdotool key BackSpace")
        elif e[0] == "ret":
            L.append("xdotool key Return")
        elif e[0] == "tab":
            L.append("xdotool key Tab")
        elif e[0] == "d":
            L.append(f"sleep {e[1]:.3f}")
        elif e[0] == "m":
            L.append(f"xdotool mousemove {e[1]} {e[2]}")
    return "\n".join(L) + "\n"


def move(x, y, dur=None, seed=None):
    x0, y0 = pos()
    pts = mover.trayecto(x0, y0, x, y, dur, random.Random(seed))
    plan = []
    for px, py in pts:
        plan += [("m", px, py), ("d", 0.022)]
    ssh(plan_to_script(plan))


def click(dc=False):
    ssh("xdotool click --repeat 2 --delay 60 1" if dc else "xdotool click 1")


def type_human(text, wpm=55.0, typos=0.015, seed=None, in_title=None):
    require_focus(in_title)
    ssh(plan_to_script(tipear.plan(text, wpm, typos, random.Random(seed))))


def typeurl(url, wpm=45.0, in_title=None):
    # El navegador autocompleta en línea con el historial y Enter navegaría a lo autocompletado, no a lo
    # tecleado (medido, doc 07 nº 29). Suprimir (borrado hacia delante) quita la sugerencia y no toca nada si no hay.
    require_focus(in_title)
    ssh("xdotool key ctrl+l")
    time.sleep(0.4)
    type_human(url, wpm=wpm, typos=0.02)
    time.sleep(0.3)
    ssh("xdotool key Delete")
    time.sleep(0.2)
    ssh("xdotool key Return")


def _find(word, n, sub):
    r = subprocess.run(["python3", os.path.join(HERE, "ocr_buscar.py"), word, str(n), "1", "", sub],
                       input=_ocr_words(shot(os.path.join(TMP, "_vmct.png"))), text=True, capture_output=True)
    if r.returncode == 0:
        return tuple(int(v) for v in r.stdout.strip().split(","))
    return None


def clicktext(word, n=1, dc=False, sub="", seg=6):
    """Clic humano en una palabra del invitado. Reintenta unos segundos por si aún no se ha pintado."""
    t0 = time.time()
    while time.time() - t0 < seg:
        p = _find(word, n, sub)
        if p:
            move(*p)
            time.sleep(0.25)
            click(dc)
            return p
        time.sleep(0.6)
    die(f"no encontré '{word}' en la pantalla del invitado tras {seg}s")


def selecttext(word, n=1, sub="", tries=3):
    """Doble clic + copiar + comprobar + reintentar (un doble clic ciego fallaba 1 de cada 3 en apps Java)."""
    want = sub or word
    got = ""
    for _ in range(tries):
        clicktext(word, n, dc=True, sub=sub)
        time.sleep(0.4)
        ssh("xdotool key ctrl+c")
        time.sleep(0.3)
        got = ssh("xclip -selection clipboard -o 2>/dev/null", capture=True, check=False)
        if got == want:
            return True
    die(f"no pude seleccionar '{want}' tras {tries} intentos (última selección: {got[:30]!r})")


# ---------------------------------------------------------------- apps y ventanas
def launch(cmd):
    ssh(f"nohup {cmd} >/dev/null 2>&1 &")


def _wid(title):
    return ssh(f'xdotool search --onlyvisible --name {shlex.quote(title)} | head -1', capture=True, check=False)


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


def place(title, x, y, w, h):
    wid = _wid(title)
    if not wid:
        die(f"no hay ventana visible '{title}'")
    ssh(f"xdotool windowmove {wid} {x} {y}; xdotool windowsize {wid} {w} {h}")
    time.sleep(0.5)
    g = dict(l.split("=") for l in ssh(f"xdotool getwindowgeometry --shell {wid}", capture=True).splitlines())
    got = [int(g[k]) for k in ("X", "Y", "WIDTH", "HEIGHT")]
    # Las decoraciones de ventana desplazan X/Y unos píxeles: tolerancia holgada en posición, estricta en tamaño
    if abs(got[2] - w) > 12 or abs(got[3] - h) > 40:
        die(f"geometría real {got} != pedida {[x, y, w, h]}")
    return got


# ---------------------------------------------------------------- ciclo de vida
def vm_state():
    out = subprocess.run(["VBoxManage", "showvminfo", VM, "--machinereadable"], capture_output=True, text=True).stdout
    for l in out.splitlines():
        if l.startswith("VMState="):
            return l.split('"')[1]
    return "desconocido"


def start(seg=150):
    if vm_state() != "running":
        subprocess.run(["VBoxManage", "startvm", VM, "--type", "gui"], check=True, capture_output=True)
    t0 = time.time()
    while time.time() - t0 < seg:
        if ssh_ok():
            return True
        time.sleep(3)
    return False


def stop(seg=90):
    subprocess.run(["VBoxManage", "controlvm", VM, "acpipowerbutton"], capture_output=True)
    t0 = time.time()
    while time.time() - t0 < seg:
        if vm_state() == "poweroff":
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------- estado de partida
def _is_running(pattern):
    return ssh(f"pgrep -f {shlex.quote(pattern)} >/dev/null && echo si || echo no", capture=True) == "si"


def burp_up(seg=120):
    """Burp Community listo en el Dashboard. Los diálogos de arranque (proyecto temporal) salen EN CADA arranque;
    se pasan con clic verificado por OCR: Enter NO funciona en ese diálogo Swing (medido)."""
    # La VENTANA PRINCIPAL lleva "Temporary Project" en el título; los diálogos de arranque se llaman casi igual
    # ("Burp Suite Community Edition v2026.8"): comprobar solo el nombre daba un falso "ya está listo" (medido).
    if _is_running("burpsuite.jar") and _wid("Temporary Project"):
        return True
    if not _is_running("burpsuite.jar"):
        launch("burpsuite")
    t0 = time.time()
    while time.time() - t0 < seg:      # puede salir antes un aviso de ficheros temporales de un cierre sucio
        # Traer al frente la ventana de Burp que toque ANTES de mirar: si otra app (p. ej. Firefox) la tapa,
        # el OCR no ve el diálogo y se esperaba hasta el timeout (medido).
        for t in ("Delete old temporary", "Burp Suite Community"):
            w = _wid(t)
            if w:
                ssh(f"xdotool windowactivate {w}")
                time.sleep(0.4)
                break
        words = " ".join(l.split("\t")[0] for l in _ocr_words(shot()).splitlines() if "\t" in l).lower()
        # OJO al orden: el aviso modal tapa el diálogo de proyecto, pero el OCR sigue viendo el texto de
        # DEBAJO. Hay que tratar primero el modal (medido: si no, se salía creyendo que ya estaba listo).
        if "delete old temporary" in words:
            clicktext("Delete", -1)    # 'Delete' sale 3 veces (título, texto, botón): el botón es el último
            time.sleep(1.5)
            continue
        if "temporary project" in words:
            break
        time.sleep(1)
    else:
        die("Burp no mostró el diálogo de proyecto (¿EULA/edición sin aceptar? ver 00-empezar-aqui-vm.md §2)")
    clicktext("Next")
    if not waitfor("Use Burp defaults", 20):
        die("el clic en Next no avanzó")
    clicktext("Start")
    for _ in range(40):                 # el título de la ventana principal lleva "Temporary Project"
        if "Temporary Project" in ssh("xdotool search --onlyvisible --name 'Temporary Project' getwindowname 2>/dev/null | head -1",
                                       capture=True, check=False):
            return True
        time.sleep(1.5)
    die("Burp no llegó a la ventana principal")


def prepare():
    """Estado de partida estándar: lab en marcha, Burp en el Dashboard, Firefox 'demo' abierto; todo maximizado."""
    if not ssh_ok():
        die("la VM no responde por SSH (¿arrancada? vm_control.py start)")
    if not _is_running("lab_idor.py"):
        ssh("nohup python3 ~/lab/lab_idor.py >/tmp/lab.log 2>&1 &")
        time.sleep(1)
    burp_up()
    if not _is_running("firefox.*-P demo"):
        launch("firefox --no-remote -P demo")
        for _ in range(20):
            if _wid("Mozilla Firefox"):
                break
            time.sleep(1)
    for title in ("Temporary Project", "Mozilla Firefox"):
        wid = _wid(title)
        if wid:
            ssh(f"xdotool windowmove {wid} 0 29; xdotool windowsize {wid} 1600 871")
    activate("Mozilla Firefox")
    faltan = [t for t in ("Temporary Project", "Mozilla Firefox") if not _wid(t)]
    if faltan or not ssh('curl -s "http://127.0.0.1:8765/cuenta?id=1001" | grep -q usuarioA && echo ok', capture=True):
        die(f"prepare INCOMPLETO: faltan {faltan or 'el lab'}")
    print("lab:", ssh('curl -s "http://127.0.0.1:8765/cuenta?id=1001" | grep -o "Cuenta de [a-zA-Z]*"', capture=True))
    print("ventanas:", ssh("xdotool search --onlyvisible --name 'Burp Suite Community|Mozilla Firefox' getwindowname | tr '\\n' ';'",
                          capture=True))


def bootstrap():
    """Deja la VM controlable: clave SSH dedicada autorizada. Idempotente. NO adivina contraseñas:
    usa la sesión gráfica ya iniciada y escribe con VBoxManage solo LETRAS tras poner el teclado en US."""
    if not os.path.exists(KEY):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "cutly-vm", "-f", KEY], check=True)
        print(f"clave dedicada creada: {KEY}")
    if ssh_ok():
        print("ya está configurada (SSH con la clave dedicada funciona)")
        return
    pub = open(KEY + ".pub").read().strip()
    v = lambda *a: subprocess.run(["VBoxManage", "controlvm", VM, *a], check=True, capture_output=True)
    enter = lambda: (v("keyboardputscancode", "1c", "9c"), time.sleep(0.8))
    print("abriendo un terminal en el invitado (Ctrl+Alt+T) y escribiendo la clave en trozos cortos...")
    v("keyboardputscancode", "1d", "38", "14", "94", "b8", "9d"); time.sleep(3)
    # keyboardputstring asume teclado US: se pone el teclado del invitado en US primero (solo letras)
    for line in ("setxkbmap us", "mkdir -p ~/.ssh", f"echo '{pub}' >> ~/.ssh/authorized_keys",
                 "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"):
        v("keyboardputstring", line); enter()
    time.sleep(1)
    print("OK: SSH operativo" if ssh_ok() else "FALLÓ: revisa la captura (shot) y que sshd esté activo en el invitado")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)

    def opt(n, d=None, c=str):
        return c(a[a.index(n) + 1]) if n in a else d

    cmd = a[0]
    if cmd == "start":
        ok = start()
        print("OK" if ok else "TIMEOUT: la VM no respondió por SSH")
        sys.exit(0 if ok else 1)
    elif cmd == "stop":
        print("apagada" if stop() else "no se apagó a tiempo (se dejó como está)")
    elif cmd == "status":
        print(f"VM {VM}: {vm_state()} | ssh: {'sí' if ssh_ok() else 'no'}")
        if ssh_ok():
            print("pantalla:", ssh("xrandr | grep '\\*' | head -1", capture=True))
            print("ventana activa:", active_title())
    elif cmd == "bootstrap":
        bootstrap()
    elif cmd == "prepare":
        prepare()
    elif cmd == "shot":
        print(shot(a[1] if len(a) > 1 else None))
    elif cmd == "pos":
        print("%d,%d" % pos())
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
    elif cmd == "windows":
        print(ssh('for w in $(xdotool search --onlyvisible --name ""); do '
                  'n=$(xdotool getwindowname $w 2>/dev/null); [ -n "$n" ] && '
                  'echo "$w | $n | $(xdotool getwindowgeometry --shell $w | tr "\\n" " ")"; done; true', capture=True))
    elif cmd == "waitfor":
        ok = waitfor(a[1], float(a[2]) if len(a) > 2 else 20)
        print("OK" if ok else "TIMEOUT")
        sys.exit(0 if ok else 1)
    elif cmd == "clicktext":
        n = int(a[2]) if len(a) > 2 and a[2].lstrip('-').isdigit() else 1
        print("%d,%d" % clicktext(a[1], n, "dc" in a, opt("--sub", "")))
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
    elif cmd == "run":
        print(ssh(a[1], capture=True))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
