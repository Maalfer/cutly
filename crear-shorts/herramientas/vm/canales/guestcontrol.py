"""Canal `VBoxManage guestcontrol`: ejecuta en el invitado a través de las Guest Additions. NO necesita SSH, ni la
regla NAT, ni clave: sirve cuando no hay SSH (un invitado recién instalado, o uno sin servidor SSH).

Credenciales: las da el USUARIO, nunca se adivinan.
    VM_GUEST_PASSFILE=<fichero con la contraseña>   (preferido: no aparece en la lista de procesos)
    VM_GUEST_PASS=<contraseña>                      (alternativa)
Usuario: VM_USER (kali).

Detalles medidos en el código, no supuestos:
  - Lo que va tras `--` en `run` es argv[0] en unas versiones de VirtualBox y argv[1] en otras: se sondea UNA vez con
    /bin/echo y se adapta (_args_desde_argv1).
  - El código de salida del script viaja en un marcador al final de stderr: no dependemos de cómo VBoxManage
    traduzca el código del proceso invitado.
  - Un script corto va como `bash -c`; uno largo (p. ej. un plan de tecleo de 140 caracteres) se copia antes a /tmp
    del invitado (la línea de órdenes de Windows tiene un límite de 32 KB).
Estado: implementado y probado con VBoxManage simulado (pruebas/test_canales.py); pendiente de medir contra la VM
real cuando el usuario dé la contraseña (PENDIENTE.md).
"""
import os
import re
import subprocess
import tempfile
import uuid

from ..anfitrion import find_vboxmanage
from ..config import USER, VM
from .base import ENTORNO, Canal, CanalTimeout, normalizar

MAX_ARG = 6000                       # por encima, el script va por fichero
MARCA_RC = "__CUTLY_RC="
# las Guest Additions lanzan el proceso fuera de la sesión X del usuario (hay que darle su autorización de X) y en
# "/": se empieza en $HOME como con SSH, o las apps lanzadas (un terminal) abrirían en "/" (medido: prompt [/])
ENTORNO_GC = ENTORNO + ' XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"; cd "$HOME" 2>/dev/null'


class CanalGuestControl(Canal):
    nombre = "guestcontrol"

    def __init__(self, vbox=None):
        self._vbox = vbox or find_vboxmanage
        self._desde_argv1 = None

    # ---------------------------------------------------------------- credenciales
    def credenciales(self):
        pf = os.environ.get("VM_GUEST_PASSFILE")
        if pf:
            return ["--username", USER, "--passwordfile", pf]
        p = os.environ.get("VM_GUEST_PASS")
        if p:
            return ["--username", USER, "--password", p]
        return None

    def _cred(self):
        c = self.credenciales()
        if c is None:
            raise PermissionError("guestcontrol necesita la contraseña del invitado: VM_GUEST_PASSFILE (preferido) o "
                                  "VM_GUEST_PASS. La da el usuario; vm_control nunca la adivina.")
        return c

    # ---------------------------------------------------------------- VBoxManage
    def _gc(self, *args, timeout=30):
        return subprocess.run([self._vbox(), "guestcontrol", VM, *args], capture_output=True, timeout=timeout)

    def _run(self, exe, args, timeout):
        """run de un ejecutable con sus argumentos (argv[1..]), sea cual sea la convención de esta versión."""
        pre = [] if self._args_desde_argv1() else [exe]
        return self._gc("run", *self._cred(), "--exe", exe, "--profile", "--wait-stdout", "--wait-stderr",
                        "--ignore-orphaned-processes", "--timeout", str(int(timeout * 1000)), "--", *pre, *args,
                        timeout=timeout + 10)

    def _args_desde_argv1(self):
        if self._desde_argv1 is None:
            r = self._gc("run", *self._cred(), "--exe", "/bin/echo", "--wait-stdout", "--", "a", "b", timeout=30)
            salida = r.stdout.decode("utf-8", "replace").strip()
            if r.returncode or salida not in ("a b", "b"):
                raise ConnectionError(f"guestcontrol no responde (rc={r.returncode}): "
                                      f"{r.stderr.decode('utf-8', 'replace').strip()[:200]}")
            self._desde_argv1 = salida == "a b"
        return self._desde_argv1

    # ---------------------------------------------------------------- interfaz Canal
    def disponible(self):
        if self.credenciales() is None:
            return False
        try:
            self._desde_argv1 = None              # re-sondear: la VM puede haber reiniciado
            return self._args_desde_argv1() is not None
        except (ConnectionError, subprocess.TimeoutExpired, OSError):
            return False

    def ejecutar(self, script, timeout):
        cuerpo = f"{ENTORNO_GC}\n{normalizar(script)}\n"
        envuelto = f"( {cuerpo} )\nprintf '\\n{MARCA_RC}%d\\n' $? >&2\n"
        remoto = None
        if len(envuelto) > MAX_ARG:
            remoto = f"/tmp/cutly_gc_{uuid.uuid4().hex[:12]}.sh"
            if not self.enviar_texto(envuelto, remoto):
                return 255, b"", b"guestcontrol: no pude copiar el script al invitado"
            envuelto = f"bash {remoto}; rc=$?; rm -f {remoto}; exit $rc"
        try:
            r = self._run("/bin/bash", ["-c", envuelto], timeout)
        except subprocess.TimeoutExpired:
            raise CanalTimeout(f"guestcontrol no terminó en {timeout}s")
        err = r.stderr.decode("utf-8", "replace")
        m = re.search(rf"\n?{MARCA_RC}(\d+)\s*$", err)
        if not m:   # el proceso no llegó a su final (lo mató el timeout o falló VBoxManage)
            return (r.returncode or 255), r.stdout, r.stderr
        return int(m.group(1)), r.stdout, err[:m.start()].encode("utf-8")

    def traer(self, remoto, local):
        if os.path.isdir(local):
            local = os.path.join(local, os.path.basename(remoto))
        return self._gc("copyfrom", *self._cred(), remoto, local, timeout=600).returncode == 0

    def enviar(self, local, remoto):
        # Medido en VirtualBox 7.2: `copyto ORIGEN /ruta/nombre` copia y renombra a la vez; `--target-directory`
        # falla con "Destination ... already exists and is a directory".
        if remoto.endswith("/"):
            remoto += os.path.basename(local)
        return self._gc("copyto", *self._cred(), local, remoto, timeout=600).returncode == 0

    def enviar_texto(self, texto, remoto):
        d = tempfile.mkdtemp(prefix="cutly_gc_")
        local = os.path.join(d, os.path.basename(remoto))
        try:
            with open(local, "w", encoding="utf-8", newline="\n") as f:
                f.write(texto)
            return self.enviar(local, remoto)
        finally:
            os.remove(local)
            os.rmdir(d)

    def describir(self):
        cred = "con credenciales" if self.credenciales() else "SIN credenciales (VM_GUEST_PASSFILE / VM_GUEST_PASS)"
        return f"guestcontrol ({USER}, {cred})"
