"""Ciclo de vida de la VM: arrancar, apagar, guardar/reanudar estado (savestate, NO snapshots), resolución y montaje
inicial (bootstrap: regla NAT + clave SSH dedicada; nunca adivina contraseñas)."""
import os
import subprocess
import time

from . import grabacion, info
from .anfitrion import vbox
from .canales.guestcontrol import CanalGuestControl
from .canales.ssh import CanalSSH, diagnosticar
from .config import KEY, PORT, VM, contrasena_invitado, die
from .conexion import describir, ssh_ok


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


def esperar(seg=150, eco=print):
    """Espera por FASES a que la VM esté controlable y dice en cuál se queda (en vez de esperar a ciegas):
    arrancando -> Guest Additions listas -> sesión iniciada (la inicia el usuario) -> el canal responde.
    Devuelve (ok, fase)."""
    t0, fase = time.time(), None
    while time.time() - t0 < seg:
        r = info.resumen()
        if r["estado"] != "running":
            nueva = f"VM {r['estado']}"
        elif not r["nivel_adiciones"]:
            nueva = "arrancando (aún sin Guest Additions)"
        elif r["sesion"] is False:
            nueva = "esperando a que INICIES SESIÓN en la VM (la contraseña la pones tú)"
        elif ssh_ok():
            eco(f"[start] listo: {describir()}")
            return True, "lista"
        else:
            nueva = "sesión iniciada; esperando al canal (" + describir() + ")"
        if nueva != fase:
            eco(f"[start] {nueva}")
            fase = nueva
        time.sleep(3)
    return False, fase


def iniciar_sesion(seg=60):
    """Inicia la sesión del escritorio desde la pantalla de login, con la contraseña que da el usuario
    (VM_GUEST_PASSFILE / VM_GUEST_PASS). Se teclea con keyboardputstring: asume teclado US (la pantalla de login de
    Kali lo usa), así que es fiable para letras y números; con símbolos puede fallar (doc 08 nº 37).
    Verifica el resultado: la sesión debe aparecer en las propiedades del invitado."""
    r = info.resumen()
    if r["sesion"]:
        return True
    if r["estado"] != "running" or not r["nivel_adiciones"]:
        die("la VM no está lista para iniciar sesión (vm_control.py start)")
    pw = contrasena_invitado()
    if not pw:
        die("para iniciar sesión hace falta la contraseña que des TÚ: VM_GUEST_PASSFILE=<fichero> (o VM_GUEST_PASS)")
    if not pw.isalnum():
        print("[login] aviso: la contraseña tiene símbolos; keyboardputstring asume teclado US y podría alterarlos")
    # en la pantalla de login de Kali (lightdm) el campo de la contraseña ya tiene el foco con el usuario elegido
    vbox("controlvm", VM, "keyboardputstring", pw)
    time.sleep(0.3)
    vbox("controlvm", VM, "keyboardputscancode", "1c", "9c")          # Enter
    t0 = time.time()
    while time.time() - t0 < seg:
        if info.resumen()["sesion"]:
            print(f"[login] sesión iniciada: {info.resumen()['usuarios']}")
            return True
        time.sleep(2)
    die("no apareció la sesión tras teclear la contraseña (¿contraseña distinta o el foco no estaba en el campo? "
        "mira `vm_control.py shot`)")


def start(seg=150, headless=False, login=False):
    """Arranca la VM y espera a que sea controlable. Con la VM apagada, antes deja lista la regla NAT y la grabación
    (a la última resolución del invitado: VirtualBox solo deja configurarla bien con la VM apagada)."""
    if not info.existe():
        die(f"no existe la VM '{VM}' (VM_NAME). Hay: {', '.join(info.vms()) or 'ninguna'}")
    estado = vm_state()
    if estado in ("poweroff", "aborted"):
        ensure_natpf()
        quedan = grabacion.configurar()
        print("[start] grabación:", "configurada (" + info.resumen()["grabacion"]["res"] + f"@{grabacion.FPS})"
              if not quedan else "; ".join(quedan))
    if estado != "running":
        vbox("startvm", VM, "--type", "headless" if headless else "gui")
    ok, fase = esperar(seg if not login else min(seg, 90))
    if not ok and login and "INICIES SESIÓN" in (fase or ""):
        time.sleep(3)                       # la pantalla de login tarda un poco más en aceptar teclas que en salir
        iniciar_sesion()
        ok = esperar(seg)[0]
    return ok


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


def bootstrap():
    """Monta el canal SSH: regla NAT + clave dedicada autorizada en el invitado. Idempotente. NO adivina contraseñas:
    con VM_GUEST_PASSFILE / VM_GUEST_PASS (los da el usuario) lo hace por guestcontrol, incluido arrancar sshd; sin
    ellos teclea la clave en un terminal del invitado (y sshd lo tienes que habilitar tú: pide tu contraseña)."""
    if not os.path.exists(KEY):
        os.makedirs(os.path.dirname(KEY), exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "cutly-vm", "-f", KEY], check=True)
        print(f"clave dedicada creada: {KEY}")
    if vm_state() in ("poweroff", "aborted"):
        print("regla NAT ssh:", "ok" if ensure_natpf() else "no se pudo")
    if vm_state() != "running":
        vbox("startvm", VM, "--type", "gui")
    ok, fase = esperar(180)
    if not ok and "INICIES SESIÓN" in (fase or ""):
        if not contrasena_invitado():
            die("inicia sesión en la VM (o da VM_GUEST_PASSFILE) y vuelve a ejecutar bootstrap")
        time.sleep(3)
        iniciar_sesion()
    if CanalSSH().disponible():          # bootstrap monta el canal SSH: comprobar ESE canal, no cualquiera
        print("ya está configurada (SSH con la clave dedicada funciona)")
        return
    with open(KEY + ".pub") as f:
        pub = f.read().strip()
    gc = CanalGuestControl()
    if gc.credenciales():   # Camino 1 (preferido): guestcontrol con la contraseña que da el usuario
        script = (f"mkdir -p ~/.ssh && grep -qxF '{pub}' ~/.ssh/authorized_keys 2>/dev/null || echo '{pub}' >> "
                  "~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; "
                  "sudo -n systemctl enable --now ssh 2>/dev/null || echo 'AVISO: sshd sin habilitar (sudo pide contraseña)'")
        rc, out, err = gc.ejecutar(script, 60)
        print("guestcontrol:", "ok" if rc == 0 else (err or out).decode("utf-8", "replace").strip()[:200],
              out.decode("utf-8", "replace").strip())
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
    if CanalSSH().disponible():
        print("OK: SSH operativo")
    else:
        print("FALLÓ:", diagnosticar())
