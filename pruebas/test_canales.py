"""Canales con el invitado (crear-shorts/herramientas/vm/canales/): interfaz común, selección y el canal guestcontrol
con un VBoxManage SIMULADO que ejecuta los scripts con un bash real del anfitrión (si lo hay). Sin VM."""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import util  # noqa: F401  (rutas)
from vm import conexion
from vm.canales import CANALES, Canal, CanalTimeout, base
from vm.canales import guestcontrol as gcmod
from vm.canales import ssh as sshmod

BASH = shutil.which("bash")
_RUN = subprocess.run          # el real: los parches de abajo sustituyen subprocess.run en todo el proceso


class VBoxSimulado:
    """Hace de `VBoxManage guestcontrol`: run (bash real), copyto/copyfrom (carpeta temporal = /tmp del invitado)."""

    def __init__(self, desde_argv1=True):
        self.desde_argv1 = desde_argv1
        self.tmp = tempfile.mkdtemp(prefix="invitado_")
        self.llamadas = []

    def limpiar(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def local(self, ruta_invitado):
        return ruta_invitado.replace("/tmp", self.tmp.replace("\\", "/"), 1)

    def __call__(self, cmd, capture_output=True, timeout=None, **k):
        self.llamadas.append(cmd)
        sub = cmd[3]
        if sub == "copyto":
            destino = cmd[cmd.index("--target-directory") + 1]
            shutil.copy(cmd[-1], self.local(destino))
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if sub == "copyfrom":
            shutil.copy(self.local(cmd[-2]), cmd[-1])
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        exe = cmd[cmd.index("--exe") + 1]
        args = cmd[cmd.index("--") + 1:]
        if not self.desde_argv1:
            args = args[1:]                      # convención antigua: lo primero tras -- es argv[0]
        if exe == "/bin/echo":
            # convención antigua: el sondeo "a b" llega como argv0=a, argv1=b -> echo imprime solo "b"
            return subprocess.CompletedProcess(cmd, 0, (" ".join(args) + "\n").encode(), b"")
        script = args[1].replace("/tmp/", self.local("/tmp") + "/")
        r = _RUN([BASH, "-c", script], capture_output=True, timeout=timeout)
        return subprocess.CompletedProcess(cmd, 0, r.stdout, r.stderr)   # VBoxManage: 0 aunque el script falle


@unittest.skipUnless(BASH, "hace falta bash en el anfitrión (Git Bash en Windows)")
class GuestControl(unittest.TestCase):
    def setUp(self):
        self.vb = VBoxSimulado()
        self.p = [mock.patch.object(gcmod.subprocess, "run", self.vb), mock.patch.dict(os.environ, {"VM_GUEST_PASS": "x"})]
        for p in self.p:
            p.start()
        self.c = gcmod.CanalGuestControl(vbox=lambda: "VBoxManage")

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.vb.limpiar()

    def test_codigo_salida_y_salidas_limpias(self):
        rc, out, err = self.c.ejecutar("echo hola; echo aviso >&2; exit 3", 20)
        self.assertEqual((rc, out.strip(), err.strip()), (3, b"hola", b"aviso"))   # sin el marcador en stderr

    def test_entorno_de_la_sesion_grafica(self):
        rc, out, _ = self.c.ejecutar('echo "$DISPLAY $LC_ALL"', 20)
        self.assertEqual(out.strip(), b":0 C.UTF-8")

    def test_script_largo_va_por_fichero_y_conserva_heredoc(self):
        relleno = "#" + "x" * gcmod.MAX_ARG + "\n"
        script = relleno + "cat <<'__PLAN__'\nlinea uno\nlinea dos\n__PLAN__\n"
        rc, out, _ = self.c.ejecutar(script, 20)
        self.assertEqual((rc, out.decode().split()), (0, ["linea", "uno", "linea", "dos"]))
        self.assertTrue(any(c[3] == "copyto" for c in self.vb.llamadas))
        self.assertEqual(os.listdir(self.vb.tmp), [])                              # el script se borra solo

    def test_convencion_antigua_de_argv0(self):
        vb = VBoxSimulado(desde_argv1=False)
        with mock.patch.object(gcmod.subprocess, "run", vb):
            c = gcmod.CanalGuestControl(vbox=lambda: "VBoxManage")
            rc, out, _ = c.ejecutar("echo ok", 20)
        vb.limpiar()
        self.assertEqual((rc, out.strip()), (0, b"ok"))

    def test_enviar_con_otro_nombre_renombra(self):
        d = tempfile.mkdtemp()
        f = os.path.join(d, "origen.txt")
        with open(f, "w") as fh:
            fh.write("dato")
        self.assertTrue(self.c.enviar(f, "/tmp/destino.txt"))
        shutil.rmtree(d)
        self.assertEqual(os.listdir(self.vb.tmp), ["destino.txt"])

    def test_passwordfile_preferido(self):
        with mock.patch.dict(os.environ, {"VM_GUEST_PASSFILE": "/f", "VM_GUEST_PASS": "x"}):
            self.assertEqual(self.c.credenciales()[2:], ["--passwordfile", "/f"])


class SinCredenciales(unittest.TestCase):
    def test_nunca_adivina(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            c = gcmod.CanalGuestControl(vbox=lambda: "VBoxManage")
            self.assertFalse(c.disponible())
            with self.assertRaises(PermissionError):
                c.ejecutar("true", 5)


class Ssh(unittest.TestCase):
    def test_comando_y_bytes_con_saltos_unix(self):
        visto = {}

        def run(cmd, input=None, capture_output=True, timeout=None):
            visto.update(cmd=cmd, input=input)
            return subprocess.CompletedProcess(cmd, 0, b"ok", b"")
        with mock.patch.object(sshmod.subprocess, "run", run):
            rc, out, _ = sshmod.CanalSSH().ejecutar("echo a\r\necho b", 5)
        self.assertEqual(rc, 0)
        self.assertIn(base.ENTORNO, visto["cmd"][-1])
        self.assertEqual(visto["input"], b"echo a\necho b")

    def test_timeout_se_traduce(self):
        def run(*a, **k):
            raise subprocess.TimeoutExpired("ssh", 1)
        with mock.patch.object(sshmod.subprocess, "run", run):
            with self.assertRaises(CanalTimeout):
                sshmod.CanalSSH().ejecutar("sleep 9", 1)


class Falso(Canal):
    nombre = "falso"
    responde = True

    def disponible(self):
        return self.responde

    def ejecutar(self, script, timeout):
        return (0, f"[{self.nombre}] {script}".encode(), b"")


class Seleccion(unittest.TestCase):
    def setUp(self):
        conexion.reiniciar()

    def tearDown(self):
        conexion.reiniciar()

    def canales(self, ssh_responde, gc_responde):
        a = type("A", (Falso,), {"nombre": "ssh", "responde": ssh_responde})
        b = type("B", (Falso,), {"nombre": "guestcontrol", "responde": gc_responde})
        return mock.patch.dict(CANALES, {"ssh": a, "guestcontrol": b})

    def test_auto_prefiere_ssh(self):
        with self.canales(True, True), mock.patch.dict(os.environ, {"VM_CANAL": "auto"}):
            self.assertEqual(conexion.ssh("x", capture=True), "[ssh] x")

    def test_auto_cae_a_guestcontrol_sin_ssh(self):
        with self.canales(False, True), mock.patch.dict(os.environ, {"VM_CANAL": "auto"}):
            self.assertTrue(conexion.ssh_ok())
            self.assertEqual(conexion.ssh("x", capture=True), "[guestcontrol] x")

    def test_canal_fijado(self):
        with self.canales(True, True), mock.patch.dict(os.environ, {"VM_CANAL": "guestcontrol"}):
            self.assertEqual(conexion.canal().nombre, "guestcontrol")

    def test_canal_inexistente(self):
        with mock.patch.dict(os.environ, {"VM_CANAL": "telepatia"}), self.assertRaises(SystemExit):
            conexion.canal()

    def test_ninguno_responde(self):
        with self.canales(False, False), mock.patch.dict(os.environ, {"VM_CANAL": "auto"}):
            self.assertFalse(conexion.ssh_ok())


if __name__ == "__main__":
    unittest.main()
