"""El material (nucleo/material.py + editor/comun/material.py): papeles, manifiesto, traer archivos (enlace o copia) y
lo que la interfaz le pide a Claude según el papel. Todo en carpetas temporales: nunca toca editor/crudo/ real."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from util import REPO  # noqa: E402

from nucleo import material, rutas  # noqa: E402
from nucleo.ffmpeg import localizar  # noqa: E402

FF = localizar("ffmpeg")


def video(ruta, w, h, segundos=1, voz=True):
    """Un vídeo sintético (con un tono si voz, o con pista MUDA como el Short de pantalla)."""
    audio = ["-f", "lavfi", "-i", "sine=frequency=440"] if voz else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30", *audio,
                    "-t", str(segundos), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", ruta],
                   check=True)
    return ruta


class Carpeta(unittest.TestCase):
    """Cada prueba con su propio editor/crudo/ temporal."""

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.crudo = os.path.join(self.d.name, "crudo")
        self.fuera = os.path.join(self.d.name, "fuera")
        os.makedirs(self.fuera)
        self.p = mock.patch.object(rutas, "CRUDO", self.crudo)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.d.cleanup()


class Roles(unittest.TestCase):
    def test_inferir(self):
        i = material.inferir_rol
        self.assertEqual(i("x.mp4", {"ancho": 1080, "alto": 1920, "audio": False}), "pantalla")
        self.assertEqual(i("cara.mp4", {"ancho": 1080, "alto": 1920, "audio": True, "duracion": 202, "fps": 60}), "cara")
        self.assertEqual(i("short_X_editado.mp4", {"ancho": 1080, "alto": 1920, "audio": True, "duracion": 73,
                                                   "fps": 60}), "short")
        self.assertEqual(i("d.mp4", {"ancho": 1920, "alto": 1080, "audio": True, "duracion": 7200}), "directo")
        self.assertEqual(i("t.mp4", {"ancho": 1920, "alto": 1012, "audio": False}, hay_registro=True), "toma")
        self.assertEqual(i("v.wav", {"audio": True}), "audio")
        self.assertEqual(i("f.png", {}), "imagen")


@unittest.skipUnless(FF, "hace falta ffmpeg")
class Manifiesto(Carpeta):
    def test_pista_muda_es_pantalla(self):
        """El Short de pantalla lleva una pista de audio muda: no por eso es la cara (fallo real corregido)."""
        os.makedirs(self.crudo)
        video(os.path.join(self.crudo, "p.mp4"), 108, 192, voz=False)
        video(os.path.join(self.crudo, "c.mp4"), 108, 192, segundos=2)
        roles = {e["archivo"]: e["rol"] for e in material.sincronizar()["material"]}
        self.assertEqual(roles, {"p.mp4": "pantalla", "c.mp4": "cara"})    # vertical con voz a 30 fps -> cara

    def test_traer_enlaza_y_fijar_rol_manda(self):
        origen = video(os.path.join(self.fuera, "mi cara.mp4"), 108, 192)
        destino = material.anadir(origen)
        self.assertEqual(os.path.dirname(destino), self.crudo)
        self.assertEqual(os.stat(destino).st_nlink, 2)                     # mismo disco: enlace, no copia
        material.fijar_rol(destino, "cara")
        e = material.sincronizar()["material"][0]
        self.assertEqual((e["rol"], e["rol_manual"]), ("cara", True))      # sincronizar respeta lo fijado
        self.assertEqual(material.por_rol("cara"), [destino])
        # soltar otra vez EL MISMO archivo no lo duplica; otro distinto con el mismo nombre no pisa nada
        self.assertEqual(material.anadir(origen), destino)
        otro = video(os.path.join(self.d.name, "mi cara.mp4"), 108, 192, segundos=2)
        self.assertTrue(material.anadir(otro).endswith("mi cara-2.mp4"))

    def test_lo_ultimo_asignado_va_primero(self):
        a = material.anadir(video(os.path.join(self.fuera, "a.mp4"), 108, 192))
        b = material.anadir(video(os.path.join(self.fuera, "b.mp4"), 108, 192))
        material.fijar_rol(b, "cara")
        with mock.patch.object(material, "datetime") as dt:
            dt.now.return_value.isoformat.return_value = "2999-01-01T00:00:00"
            material.fijar_rol(a, "cara")
        self.assertEqual(material.por_rol("cara")[0], a)

    def test_quitar_del_disco_lo_quita_del_manifiesto(self):
        a = material.anadir(video(os.path.join(self.fuera, "a.mp4"), 108, 192))
        material.sincronizar()
        os.remove(a)
        self.assertEqual(material.sincronizar()["material"], [])
        self.assertTrue(os.path.exists(os.path.join(self.fuera, "a.mp4")))   # el original sigue

    def test_cli(self):
        a = material.anadir(video(os.path.join(self.fuera, "a.mp4"), 108, 192))
        env = dict(os.environ, CUTLY_CRUDO=self.crudo, PYTHONUTF8="1")
        cli = os.path.join(REPO, "editor", "comun", "material.py")
        r = subprocess.run([sys.executable, cli, "rol", a, "directo"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, cli, "ruta", "directo"], capture_output=True, text=True, env=env)
        self.assertEqual(r.stdout.strip(), a)


try:
    from PySide6.QtWidgets import QApplication
    HAY_QT = True
except ImportError:
    HAY_QT = False


@unittest.skipUnless(HAY_QT, "PySide6 no instalado")
class Interfaz(unittest.TestCase):
    def test_acciones_segun_el_papel(self):
        from estudio.paneles.material import acciones_claude
        c, p = os.path.join(REPO, "editor", "crudo", "c.mp4"), os.path.join(REPO, "editor", "crudo", "p.mp4")
        acciones = dict(acciones_claude([c, p], ["cara", "pantalla"]))
        self.assertEqual(acciones["Fusionar cara + pantalla"],
                         "/fusionar-cara-pantalla editor/crudo/c.mp4 editor/crudo/p.mp4")
        self.assertTrue(acciones["Preguntar a Claude por esto…"].endswith(" "))   # se deja escrito para completarlo
        self.assertIn("/directo-a-clips", dict(acciones_claude([c], ["directo"]))["Proponer clips de c.mp4"])

    def test_titulo_y_rutas_para_claude(self):
        from estudio.entorno import para_claude
        from estudio.paneles.fusion import titulo_valido
        self.assertTrue(titulo_valido("Entrar-Por-SSH-Sin-Saber-La-Contrasena"))
        self.assertFalse(titulo_valido("entrar por ssh"))
        self.assertFalse(titulo_valido("Contraseña-Ñ"))
        self.assertEqual(para_claude(os.path.join(REPO, "editor", "crudo", "mi cara.mp4")), '"editor/crudo/mi cara.mp4"')


@unittest.skipUnless(HAY_QT and FF, "PySide6 y ffmpeg")
class Ranura(Carpeta):
    def test_soltar_en_la_ranura_trae_y_fija_el_papel(self):
        from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
        from PySide6.QtGui import QDragEnterEvent, QDropEvent
        app = QApplication.instance() or QApplication([])
        from estudio.paneles.ranura import Ranura as RanuraW
        origen = video(os.path.join(self.fuera, "yo.mp4"), 108, 192)
        r = RanuraW("cara", "Cara", "tu cara")
        cambios = []
        r.cambiado.connect(cambios.append)
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(origen)])
        args = (Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(r, QDragEnterEvent(QPoint(5, 5), *args))
        QApplication.sendEvent(r, QDropEvent(QPointF(5, 5), *args))
        t = QTimer(singleShot=True, interval=15000, timeout=app.quit)
        t.start()
        r.cambiado.connect(lambda ruta: ruta and QCoreApplication.instance().quit())
        app.exec()
        destino = os.path.join(self.crudo, "yo.mp4")
        self.assertEqual(r.ruta, destino)
        e = material.cargar()["material"][0]
        self.assertEqual((e["archivo"], e["rol"], e["rol_manual"]), ("yo.mp4", "cara", True))


if __name__ == "__main__":
    unittest.main()


class Candidatos(unittest.TestCase):
    """Propuesta de fragmentos de un directo (nucleo/candidatos.py) y lo que la sección le dice a Claude."""

    def test_validar(self):
        from nucleo import candidatos
        bien = {"fragmentos": [{"n": 1, "inicio": 10, "fin": 90, "titulo": "A", "tema": "x"}]}
        self.assertEqual(candidatos.validar(bien), [])
        mal = {"fragmentos": [{"n": 1, "inicio": 90, "fin": 10, "titulo": "A", "tema": "x"},
                              {"n": 1, "inicio": 1, "fin": 2, "titulo": "B", "tema": "y"}, {"n": 3}]}
        self.assertEqual(len(candidatos.validar(mal)), 3)
        self.assertEqual(candidatos.hhmmss(3725), "01:02:05")

    @unittest.skipUnless(HAY_QT, "PySide6 no instalado")
    def test_mensaje_de_los_elegidos(self):
        from estudio.paneles.directo import mensaje_elegidos
        d = {"directo": "d.mp4", "fragmentos": [{"n": 1, "titulo": "Uno", "elegido": False},
                                                {"n": 4, "titulo": "Cuatro", "elegido": True}]}
        m = mensaje_elegidos(os.path.join(REPO, "editor", "crudo", "d.candidatos.json"), d)
        self.assertIn("fragmentos 4 (Cuatro)", m)
        self.assertIn("editor/crudo/d.candidatos.json", m)
        self.assertIsNone(mensaje_elegidos("x", {"fragmentos": [{"n": 1, "titulo": "U"}]}))


@unittest.skipUnless(HAY_QT and FF, "PySide6 y ffmpeg")
class RepartoFusion(Carpeta):
    def test_mudo_a_pantalla_con_voz_a_cara(self):
        from estudio.paneles.fusion import papel_para_fusion
        self.assertEqual(papel_para_fusion(video(os.path.join(self.fuera, "p.mp4"), 108, 192, voz=False)), "pantalla")
        self.assertEqual(papel_para_fusion(video(os.path.join(self.fuera, "c.mp4"), 108, 192)), "cara")


@unittest.skipUnless(FF, "hace falta ffmpeg")
class ShortManual(Carpeta):
    def test_plan_json_monta_el_short(self):
        """construir_short.py ya no se edita: monta desde un plan (y la banda de la cara mide 648)."""
        os.makedirs(self.crudo)
        fuente = video(os.path.join(self.crudo, "g.mp4"), 1920, 1080, segundos=2, voz=False)
        salida = os.path.join(self.d.name, "short_Prueba_editado.mp4")
        plan = os.path.join(self.d.name, "plan.json")
        from nucleo import archivos
        archivos.escribir_json(plan, {"salida": salida, "fuentes": {"g": fuente}, "vbitrate": "2M",
                                      "segmentos": [{"src": "g", "start": 0, "end": 1.5, "cx": 500, "cy": 50,
                                                     "cw": 816, "ch": 961}]})
        r = subprocess.run([sys.executable, os.path.join(REPO, "editor", "shorts", "construir_short.py"), plan],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        from nucleo import medios
        self.assertEqual(medios.probe_video(salida)[:2], (1080, 1920))
        fila_banda = medios.fotograma_gris(salida, 0.5)[640]
        self.assertLess(int(fila_banda.max()), 24)                  # filas 0-647: la banda negra de la cara
