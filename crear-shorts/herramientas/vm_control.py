#!/usr/bin/env python3
"""
vm_control.py — Controla una VM Linux (X11) de VirtualBox con entrada HUMANA, desde el anfitrión.

Reutiliza el MISMO plan de pulsaciones y trayectos que en macOS (tipear.plan, mover.trayecto); solo
cambia el emisor: en vez de CGEvent (teclear.swift) usa `xdotool` dentro del invitado, por SSH.
Las capturas las da VirtualBox (`controlvm screenshotpng`, sin permisos del anfitrión, ~0,08 s).

Por qué así (medido, doc 08): `VBoxManage controlvm keyboardputstring` asume teclado US y CORROMPE
el texto con otra distribución (se perdían comillas, | ~ ? y las tildes); VBoxManage no tiene
comando de ratón. `xdotool` dentro del invitado escribe Unicode con cualquier layout y mueve el ratón.

Requisitos: VM con Guest Additions, sshd, `xdotool` y sesión X11; una clave SSH autorizada.
Variables:  VM_NAME (def. kali)  VM_KEY (ruta a la clave)  VM_SSH_PORT (def. 2222)  VM_USER (def. kali)

Uso:
  vm_control.py shot [salida.png]            captura de la pantalla del invitado
  vm_control.py pos                          posición del cursor del invitado
  vm_control.py move X Y [--dur S] [--seed N]   mueve con trayecto humano
  vm_control.py click [dc]                   clic izquierdo (dc = doble clic) en la posición actual
  vm_control.py type "texto" [--wpm 55] [--typos 0.015] [--seed N]
  vm_control.py key Return | ctrl+alt+t ...  pulsaciones sueltas (sintaxis xdotool)
  vm_control.py windows                      ventanas visibles con geometría
  vm_control.py run "comando"                ejecuta un comando en el invitado (con DISPLAY=:0)
  vm_control.py waitfor "texto" [seg]        espera (OCR sobre capturas) a que aparezca un texto
  vm_control.py clicktext PALABRA [n] [dc] [--sub TROZO]   mueve (humano) y clica una palabra de la pantalla
"""
import os
import random
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tipear   # plan() de pulsaciones humanas
import mover    # trayecto() de ratón humano

VM = os.environ.get("VM_NAME", "kali")
KEY = os.environ.get("VM_KEY", os.path.expanduser("~/.ssh/cutly_vm"))
PORT = os.environ.get("VM_SSH_PORT", "2222")
USER = os.environ.get("VM_USER", "kali")


def ssh(script, capture=False):
    # LC_ALL=C.UTF-8 es IMPRESCINDIBLE: sin locale UTF-8, xdotool descarta los caracteres no ASCII
    # ("Invalid multi-byte sequence") y desaparecen las tildes, ñ, € y ¿ (error real medido).
    cmd = ["ssh", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           "-p", PORT, f"{USER}@127.0.0.1", "export DISPLAY=:0 LC_ALL=C.UTF-8 LANG=C.UTF-8; bash -s"]
    r = subprocess.run(cmd, input=script, text=True, capture_output=True)
    if r.returncode:
        sys.exit(f"ssh falló: {r.stderr.strip()}")
    return r.stdout.strip() if capture else None


def shot(path="/tmp/vm.png"):
    subprocess.run(["VBoxManage", "controlvm", VM, "screenshotpng", path], check=True)
    return path


def pos():
    out = ssh("xdotool getmouselocation --shell", capture=True)
    d = dict(l.split("=") for l in out.splitlines() if "=" in l)
    return int(d["X"]), int(d["Y"])


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


def type_human(text, wpm=55.0, typos=0.015, seed=None):
    ssh(plan_to_script(tipear.plan(text, wpm, typos, random.Random(seed))))


def _ocr_words(png):
    kit = os.environ.get("CTRL_KIT", os.path.expanduser("~/Desktop/ctrl-kit"))
    return subprocess.run([os.path.join(kit, "ocr"), "--words", png], capture_output=True, text=True).stdout


def waitfor(text, seg=20):
    """Espera a que `text` aparezca en la pantalla del invitado (OCR por línea sobre capturas)."""
    kit = os.environ.get("CTRL_KIT", os.path.expanduser("~/Desktop/ctrl-kit"))
    t0 = __import__("time").time()
    while __import__("time").time() - t0 < seg:
        shot("/tmp/_vmwait.png")
        out = subprocess.run([os.path.join(kit, "ocr"), "/tmp/_vmwait.png"], capture_output=True, text=True).stdout
        if text.lower() in out.lower():
            return True
        __import__("time").sleep(0.7)
    return False


def clicktext(word, n=1, dc=False, sub="", seg=6):
    """Clic humano en una palabra del invitado. Reintenta unos segundos por si aún no se ha pintado."""
    import time
    here = os.path.dirname(os.path.abspath(__file__))
    t0 = time.time()
    while time.time() - t0 < seg:
        shot("/tmp/_vmct.png")
        r = subprocess.run(["python3", os.path.join(here, "ocr_buscar.py"), word, str(n), "1", "", sub],
                           input=_ocr_words("/tmp/_vmct.png"), text=True, capture_output=True)
        if r.returncode == 0:
            x, y = (int(v) for v in r.stdout.strip().split(","))
            move(x, y)
            time.sleep(0.25)
            ssh("xdotool click --repeat 2 --delay 60 1" if dc else "xdotool click 1")
            return (x, y)
        time.sleep(0.6)
    sys.exit(f"no encontré '{word}' en la pantalla del invitado tras {seg}s")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    def opt(n, d=None, c=str):
        return c(a[a.index(n) + 1]) if n in a else d
    cmd = a[0]
    if cmd == "shot":
        print(shot(a[1] if len(a) > 1 else "/tmp/vm.png"))
    elif cmd == "pos":
        print("%d,%d" % pos())
    elif cmd == "move":
        move(int(a[1]), int(a[2]), opt("--dur", None, float), opt("--seed", None, int))
    elif cmd == "click":
        ssh("xdotool click --repeat 2 --delay 60 1" if "dc" in a else "xdotool click 1")
    elif cmd == "type":
        type_human(a[1], opt("--wpm", 55.0, float), opt("--typos", 0.015, float), opt("--seed", None, int))
    elif cmd == "key":
        ssh("xdotool key " + " ".join(shlex.quote(k) for k in a[1:]))
    elif cmd == "windows":
        print(ssh('for w in $(xdotool search --onlyvisible --name ""); do '
                  'n=$(xdotool getwindowname $w 2>/dev/null); [ -n "$n" ] && '
                  'echo "$w | $n | $(xdotool getwindowgeometry --shell $w | tr "\\n" " ")"; done', capture=True))
    elif cmd == "waitfor":
        ok = waitfor(a[1], float(a[2]) if len(a) > 2 else 20)
        print("OK" if ok else "TIMEOUT")
        sys.exit(0 if ok else 1)
    elif cmd == "clicktext":
        print("%d,%d" % clicktext(a[1], int(a[2]) if len(a) > 2 and a[2].isdigit() else 1, "dc" in a, opt("--sub", "")))
    elif cmd == "run":
        print(ssh(a[1], capture=True))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
