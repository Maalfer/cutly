"""cutly estudio (estudio/): flujos = skills, lógica de la pestaña Subtítulos, el pseudo-terminal y los paneles sin
mostrarlos (plataforma Qt "offscreen"). No abre ninguna sesión de Claude Code."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import util  # noqa: F401,E402  (rutas)

try:
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtWidgets import QApplication
    HAY_QT = True
except ImportError:                       # la app es opcional: sin PySide6 no se prueba
    HAY_QT = False

from nucleo import archivos  # noqa: E402


def app():
    return QApplication.instance() or QApplication([])


@unittest.skipUnless(HAY_QT, "PySide6 no instalado (pip install -r estudio/requisitos.txt)")
class Flujos(unittest.TestCase):
    def test_cada_skill_es_un_boton(self):
        from estudio.flujos import ROTULOS, SKILLS, flujos
        fs = flujos()
        nombres = [f["nombre"] for f in fs]
        self.assertEqual(sorted(nombres), sorted(os.listdir(SKILLS)))      # el nombre coincide con su carpeta
        for f in fs:
            self.assertTrue(f["descripcion"], f["nombre"])                  # Claude decide con la descripción
            self.assertEqual(f["comando"], "/" + f["nombre"])
        self.assertTrue(set(ROTULOS) <= set(nombres))
        self.assertEqual(nombres[: len(ROTULOS)], list(ROTULOS))           # el orden de la barra


@unittest.skipUnless(HAY_QT, "PySide6 no instalado")
class LogicaSubtitulos(unittest.TestCase):
    BLOQUES = [{"ini": 0.0, "fin": 0.8, "texto": "Hoy vas", "palabras": []},
               {"ini": 0.9, "fin": 1.5, "texto": "a conocer", "palabras": []}]

    def test_bloque_en(self):
        from estudio.paneles.subtitulos import bloque_en
        self.assertEqual([bloque_en(self.BLOQUES, t) for t in (-1, 0.0, 0.88, 1.2, 9)], [-1, 0, 1, 1, 1])

    def test_aplicar_textos_solo_toca_el_texto(self):
        from estudio.paneles.subtitulos import aplicar_textos
        d = aplicar_textos({"bloques": [dict(b) for b in self.BLOQUES]}, ["Hoy  vas", "a conocer una"])
        self.assertEqual([b["texto"] for b in d["bloques"]], ["Hoy vas", "a conocer una"])
        self.assertEqual(d["bloques"][1]["ini"], 0.9)

    def test_video_de(self):
        from estudio.paneles.subtitulos import video_de
        with tempfile.TemporaryDirectory() as d:
            j = os.path.join(d, "short_X_editado.subtitulos.json")
            self.assertEqual(video_de(j, {}), os.path.join(d, "short_X_editado.mp4"))
            open(os.path.join(d, "otro.mp4"), "w").close()
            self.assertEqual(video_de(j, {"video": "otro.mp4"}), os.path.join(d, "otro.mp4"))


@unittest.skipUnless(HAY_QT, "PySide6 no instalado")
class Pty(unittest.TestCase):
    def test_programa_en_pseudo_terminal(self):
        from estudio.terminal.pty import ProcesoPty
        app()
        with tempfile.TemporaryDirectory() as d:
            prog = os.path.join(d, "p.py")
            with open(prog, "w", encoding="utf-8") as f:
                f.write("import os,time\nprint('hola ñandú', os.get_terminal_size(), flush=True)\ntime.sleep(0.5)\n")
            p = ProcesoPty([sys.executable, prog])
            buf = []

            def llega(texto):
                buf.append(texto)
                if "\x1b[c" in texto:            # ConPTY pregunta "¿qué terminal eres?": xterm.js lo contesta solo
                    p.escribir("\x1b[?1;2c")
            p.salida.connect(llega)
            p.terminado.connect(lambda _c: QCoreApplication.instance().quit())
            p.iniciar(90, 25)
            QTimer.singleShot(15000, QCoreApplication.instance().quit)
            QCoreApplication.instance().exec()
            p.cerrar()
        salida = "".join(buf)
        self.assertIn("hola ñandú", salida)
        self.assertIn("columns=90, lines=25", salida)


@unittest.skipUnless(HAY_QT, "PySide6 no instalado")
class PanelSubtitulos(unittest.TestCase):
    def setUp(self):
        app()
        from estudio.paneles import subtitulos as modulo
        self.modulo = modulo
        self.d = tempfile.TemporaryDirectory()
        self.salida_orig = modulo.SALIDA
        modulo.SALIDA = self.d.name
        self.json = os.path.join(self.d.name, "short_X_editado.subtitulos.json")
        archivos.escribir_json(self.json, {"video": "short_X_editado.mp4", "bloques": [
            {"ini": 0.0, "fin": 0.8, "texto": "Hoy vas", "palabras": [[0.0, 0.4, "Hoy"], [0.4, 0.8, "vas"]]},
            {"ini": 0.9, "fin": 1.5, "texto": "a conoser", "palabras": [[0.9, 1.1, "a"], [1.1, 1.5, "conoser"]]}]})

    def tearDown(self):
        self.modulo.SALIDA = self.salida_orig
        self.d.cleanup()

    def test_revisar_guardar_y_avisar(self):
        p = self.modulo.PanelSubtitulos()
        self.assertEqual(p.tabla.rowCount(), 2)
        p._sigue(1.0)                                         # resaltar mientras suena
        self.assertFalse(p.sucio)                             # ...no es editar
        p.tabla.item(1, 3).setText("a conocer")               # corrección del usuario
        self.assertTrue(p.sucio)
        mensajes = []
        p.pedir.connect(mensajes.append)
        p.revisado()                                          # guarda y avisa a Claude
        self.assertFalse(p.sucio)
        self.assertEqual(archivos.leer_json(self.json)["bloques"][1]["texto"], "a conocer")
        self.assertIn("short_X_editado.subtitulos.json", mensajes[0])
        self.assertIn("quemarlos", mensajes[0])


if __name__ == "__main__":
    unittest.main()
