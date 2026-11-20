"""Integración con VirtualBox sin VM: lectura de showvminfo / guestproperty (con salidas REALES copiadas de VirtualBox
7.2 con un invitado Kali), detección de sesión, configuración de la grabación, clasificación de fallos de SSH y reglas
del diagnóstico `doctor`."""
import os
import struct
import tempfile
import unittest
import zlib

import util  # noqa: F401  (rutas)
from vm import diagnostico, grabacion, info
from vm.canales.ssh import clasificar

# extractos reales (2026-11-19): VM en la pantalla de login
SHOWVMINFO = '''name="kali"
VMState="running"
Forwarding(0)="ssh,tcp,127.0.0.1,2222,,22"
recording_started="off"
rec_screen_dest_filename="C:\\\\Users\\\\mario\\\\VirtualBox VMs\\\\kali\\\\kali-screen0.webm"
rec_screen_video_res_xy="1024x768"
rec_screen_video_rate_kbps=512
rec_screen_video_fps=25
GuestAdditionsRunLevel=2
GuestAdditionsVersion="6.0.0 r127566"
'''
PROPIEDADES = '''/VirtualBox/GuestAdd/Version            = '7.2.20'                       @ 2026-11-15T11:33:06.909Z
/VirtualBox/GuestInfo/Net/0/V4/IP       = '10.0.2.15'                    @ 2026-11-19T20:10:08.090Z
/VirtualBox/GuestInfo/OS/LoggedInUsers     = '1'                            @ 2026-11-19T20:11:39.901Z TRANSIENT, TRANSRESET
/VirtualBox/GuestInfo/OS/LoggedInUsersList = 'lightdm'                      @ 2026-11-19T20:10:08.090Z TRANSIENT, TRANSRESET
'''


class Lectura(unittest.TestCase):
    def test_showvminfo_con_rutas_escapadas(self):
        m = info.parsear_maquina(SHOWVMINFO)
        self.assertEqual(m["VMState"], "running")
        self.assertEqual(m["rec_screen_dest_filename"], r"C:\Users\mario\VirtualBox VMs\kali\kali-screen0.webm")

    def test_propiedades(self):
        p = info.parsear_propiedades(PROPIEDADES)
        self.assertEqual(p["/VirtualBox/GuestInfo/Net/0/V4/IP"], "10.0.2.15")
        self.assertEqual(p["/VirtualBox/GuestInfo/OS/LoggedInUsersList"], "lightdm")

    def test_la_pantalla_de_login_no_es_una_sesion(self):
        r = info.resumen(info.parsear_maquina(SHOWVMINFO), info.parsear_propiedades(PROPIEDADES))
        self.assertIs(r["sesion"], False)
        self.assertEqual(r["version_adiciones"], "7.2.20")          # la del servicio, no el "6.0.0" del driver
        self.assertEqual(r["ip"], "10.0.2.15")

    def test_sesion_del_usuario(self):
        p = info.parsear_propiedades(PROPIEDADES.replace("'lightdm'", "'kali'"))
        self.assertIs(info.resumen(info.parsear_maquina(SHOWVMINFO), p)["sesion"], True)

    def test_sin_propiedades_usa_el_nivel(self):
        m = info.parsear_maquina(SHOWVMINFO.replace("RunLevel=2", "RunLevel=3"))
        self.assertIs(info.resumen(m, {})["sesion"], True)

    def test_tamano_png_sin_pillow(self):
        ihdr = struct.pack(">IIBBBBB", 1920, 976, 8, 2, 0, 0, 0)
        png = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr +
               struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "x.png")
            with open(f, "wb") as fh:
                fh.write(png)
            self.assertEqual(info.tamano_png(f), (1920, 976))


class Grabacion(unittest.TestCase):
    def test_la_configuracion_por_defecto_de_virtualbox_no_sirve(self):
        cfg = info.resumen(info.parsear_maquina(SHOWVMINFO), {})["grabacion"]
        d = grabacion.diferencias(cfg, (1920, 976))
        self.assertEqual(len(d), 3)                                   # resolución, fps y calidad

    def test_configuracion_buena(self):
        cfg = {"res": "1920x976", "fps": "30", "kbps": "25000"}
        self.assertEqual(grabacion.diferencias(cfg, (1920, 976)), [])


class Ssh(unittest.TestCase):
    def test_clasifica_los_fallos_medidos(self):
        self.assertIn("no está autorizada", clasificar("kali@127.0.0.1: Permission denied (publickey,password).")[0])
        self.assertIn("sshd del INVITADO", clasificar("Connection closed by 127.0.0.1 port 2222")[0])
        self.assertIn("regla NAT", clasificar("ssh: connect to host 127.0.0.1 port 2222: Connection refused")[0])


def datos(**cambios):
    d = {"vboxmanage": "VBoxManage", "version_host": "7.2.22r175245", "existe": True, "vms": ["kali"], "clave": True,
         "puerto": "2222", "credenciales_gc": False, "toma_abierta": None,
         "anfitrion": {"ffmpeg": True, "tesseract": True, "ssh": True},
         "resumen": info.resumen(info.parsear_maquina(SHOWVMINFO), info.parsear_propiedades(PROPIEDADES.replace(
             "'lightdm'", "'kali'"))), "resolucion": (1920, 976), "canal_ok": True, "canal": "ssh",
         "invitado_faltan": [], "x11": True}
    d["resumen"]["grabacion"].update(res="1920x976", fps="30", kbps="25000")
    d.update(cambios)
    return d


def niveles(filas):
    return {punto: nivel for nivel, punto, _, _ in filas}


class Doctor(unittest.TestCase):
    def test_todo_bien(self):
        self.assertNotIn("FALLA", [f[0] for f in diagnostico.evaluar(datos())])

    def test_sin_sesion_ni_canal(self):
        d = datos(canal_ok=False, ssh_diagnostico="x")
        d["resumen"]["sesion"] = False
        n = niveles(diagnostico.evaluar(d))
        self.assertEqual((n["sesión"], n["canal"]), ("FALLA", "FALLA"))

    def test_grabacion_mal_con_la_vm_apagada_es_aviso(self):
        d = datos()
        d["resumen"].update(estado="poweroff")
        d["resumen"]["grabacion"].update(res="1024x768")
        self.assertEqual(niveles(diagnostico.evaluar(d))["grabación"], "AVISO")

    def test_guest_additions_de_otra_version(self):
        d = datos()
        d["resumen"]["version_adiciones"] = "6.1.50"
        self.assertEqual(niveles(diagnostico.evaluar(d))["Guest Additions"], "AVISO")

    def test_herramientas_que_faltan(self):
        d = datos(invitado_faltan=["xdotool", "xdpyinfo", "wmctrl"], anfitrion={"ffmpeg": True, "tesseract": False, "ssh": True})
        filas = diagnostico.evaluar(d)
        n = niveles(filas)
        self.assertEqual((n["herramientas del invitado"], n["tesseract"]), ("FALLA", "FALLA"))
        self.assertIn("x11-utils", [f[3] for f in filas if f[1] == "herramientas del invitado"][0])
        self.assertEqual(n["herramientas opcionales del invitado"], "INFO")      # wmctrl tiene alternativa

    def test_vm_inexistente(self):
        self.assertEqual(niveles(diagnostico.evaluar(datos(existe=False)))["VM"], "FALLA")


if __name__ == "__main__":
    unittest.main()
