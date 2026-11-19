"""Canal SSH (el de siempre, medido): 127.0.0.1:VM_SSH_PORT -> 22 del invitado con la clave dedicada VM_KEY.
Necesita el montaje de `vm_control.py bootstrap` (regla NAT + clave). Rápido (una conexión por llamada).

El script viaja por stdin en BYTES con \\n (en Windows, text=True lo convertiría a \\r\\n y bash fallaría).
"""
import os
import subprocess

from ..config import KEY, PORT, USER
from .base import ENTORNO, Canal, CanalTimeout, normalizar


def _ssh_cmd(extra=None):
    return ["ssh", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new", "-p", PORT, f"{USER}@127.0.0.1"] + (extra or [])


def _scp(origen, destino):
    return subprocess.run(["scp", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-P", PORT,
                           origen, destino], capture_output=True).returncode == 0


class CanalSSH(Canal):
    nombre = "ssh"

    def disponible(self):
        return subprocess.run(_ssh_cmd(["true"]), capture_output=True).returncode == 0

    def ejecutar(self, script, timeout):
        # `timeout` es OBLIGATORIO: subprocess.run espera a que el REMOTO cierre stdout/stderr; un proceso lanzado en
        # segundo plano que no se desengancha del todo (incluso con setsid) deja el canal colgado para siempre y sin
        # avisar (medido: 3+ min sin CPU, bloqueado en I/O). Mejor fallar rápido y de forma diagnosticable.
        try:
            r = subprocess.run(_ssh_cmd([f"{ENTORNO}; bash -s"]), input=normalizar(script).encode("utf-8"),
                               capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise CanalTimeout(f"ssh no cerró en {timeout}s")
        return r.returncode, r.stdout, r.stderr

    def traer(self, remoto, local):
        return _scp(f"{USER}@127.0.0.1:{remoto}", local)

    def enviar(self, local, remoto):
        return _scp(local, f"{USER}@127.0.0.1:{remoto}")

    def describir(self):
        return f"ssh ({USER}@127.0.0.1:{PORT})"


def clasificar(stderr):
    """Causa de un fallo de `ssh ... true` a partir de su mensaje (medido en este proyecto) -> (causa, solución)."""
    e = stderr.lower()
    if "permission denied" in e:
        return "la clave dedicada no está autorizada en el invitado", "vm_control.py bootstrap"
    if "connection refused" in e:
        return ("nadie escucha en el puerto del anfitrión (¿VM apagada o sin la regla NAT?)",
                "vm_control.py start (con la VM apagada añade la regla NAT)")
    if "connection closed" in e or "kex_exchange_identification" in e or "connection reset" in e:
        return ("VirtualBox acepta en el puerto pero el sshd del INVITADO no contesta (sin arrancar o sin habilitar)",
                "en un terminal del invitado: sudo systemctl enable --now ssh (te pide TU contraseña); o "
                "VM_GUEST_PASSFILE + bootstrap")
    if "timed out" in e:
        return "el invitado no contesta a tiempo (arrancando o colgado)", "espera y repite; mira `vm_control.py shot`"
    return "desconocida: " + stderr.strip()[:160], "ssh -v -i <clave> -p <puerto> <usuario>@127.0.0.1"


def diagnosticar():
    """Por qué no funciona el canal SSH, con la solución (cadena legible)."""
    if not os.path.exists(KEY):
        return f"no existe la clave dedicada {KEY} -> vm_control.py bootstrap"
    r = subprocess.run(_ssh_cmd(["true"]), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0:
        return "SSH funciona"
    causa, solucion = clasificar(r.stderr)
    return f"{causa} -> {solucion}"
