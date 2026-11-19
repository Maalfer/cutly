"""Canal SSH (el de siempre, medido): 127.0.0.1:VM_SSH_PORT -> 22 del invitado con la clave dedicada VM_KEY.
Necesita el montaje de `vm_control.py bootstrap` (regla NAT + clave). Rápido (una conexión por llamada).

El script viaja por stdin en BYTES con \\n (en Windows, text=True lo convertiría a \\r\\n y bash fallaría).
"""
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
