"""Ciclo de vida de la VM: arrancar, apagar, guardar/reanudar estado (savestate, NO snapshots), resolución y montaje
inicial (bootstrap: regla NAT + clave SSH dedicada; nunca adivina contraseñas)."""
import os
import subprocess
import time

from .anfitrion import vbox
from .config import KEY, PORT, USER, VM
from .conexion import ssh_ok


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
    with open(KEY + ".pub") as f:
        pub = f.read().strip()
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
