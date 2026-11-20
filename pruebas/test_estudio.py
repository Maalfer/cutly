"""cutly estudio (estudio/): flujos = skills, lógica de la revisión de subtítulos (dentro de Resultados), el
pseudo-terminal y los paneles sin mostrarlos (plataforma Qt "offscreen"). No abre ninguna sesión de Claude Code."""
import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import util  # noqa: F401,E402  (rutas)
from util import REPO  # noqa: E402

try:
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtWidgets import QApplication
    HAY_QT = True
except ImportError:                       # la app es opcional: sin PySide6 no se prueba
    HAY_QT = False

from nucleo import archivos  # noqa: E402


def app():
    return QApplication.instance() or QApplication([])


@unittest.skipUnless(HAY_QT, "PySide6 no instalado (pip install -r requirements.txt)")
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
class RevisorSubtitulos(unittest.TestCase):
    """RevisorSubtitulos vive dentro de Resultados (sin reproductor propio: usa el que le pasan)."""
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
        p = self.modulo.RevisorSubtitulos(None)
        p.abrir(self.json)
        self.assertEqual(p.tabla.rowCount(), 2)
        p.seguir(1.0)                                         # resaltar mientras suena
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


def _luminancia(hexa):
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a, b):
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@unittest.skipUnless(HAY_QT, "PySide6 no instalado")
class Accesibilidad(unittest.TestCase):
    def test_contraste_wcag_de_cada_tema(self):
        """Texto, texto secundario y botón principal legibles en todos los temas (WCAG AA 4,5:1; alto contraste 7:1)."""
        from estudio.apariencia import TEMAS
        for nombre, c in TEMAS.items():
            minimo = 7 if nombre == "alto contraste" else 4.5
            for texto, fondo in (("texto", "fondo"), ("texto", "panel"), ("ayuda", "fondo"), ("ayuda", "panel"),
                                 ("acento_texto", "acento")):
                self.assertGreaterEqual(contraste(c[texto], c[fondo]), minimo, f"{nombre}: {texto} sobre {fondo}")

    def test_cada_seccion_cumple_el_contrato(self):
        app()
        from estudio.paneles.directo import PanelDirecto
        from estudio.paneles.fusion import PanelFusion
        from estudio.paneles.grabacion import PanelGrabacion
        from estudio.paneles.material import PanelMaterial
        from estudio.paneles.resultados import PanelResultados
        titulos = []
        for clase in (PanelDirecto, PanelFusion, PanelGrabacion, PanelResultados, PanelMaterial):
            p = clase()
            titulos.append(p.TITULO)
            self.assertTrue(hasattr(p, "pedir"), clase.__name__)
            self.assertTrue(hasattr(p, "traer_soltados"), clase.__name__)   # todas tienen sitio para soltar
            p.deleteLater()
        self.assertEqual(len(set(titulos)), len(titulos))


@unittest.skipUnless(HAY_QT, "PySide6 no instalado")
class Motores(unittest.TestCase):
    """Sesión → Motor: alternar entre Claude Code y OpenCode en el mismo panel (estudio/motores.py)."""

    def setUp(self):
        app()
        self._ajustes_orig = os.environ.get("CUTLY_AJUSTES")
        os.environ["CUTLY_AJUSTES"] = "prueba_motores"     # no tocar las preferencias reales del usuario

    def tearDown(self):
        from PySide6.QtCore import QSettings
        QSettings("cutly", "prueba_motores").clear()        # no acumular entre tandas de pruebas
        if self._ajustes_orig is None:
            os.environ.pop("CUTLY_AJUSTES", None)
        else:
            os.environ["CUTLY_AJUSTES"] = self._ajustes_orig

    def test_motores_bien_formados(self):
        from estudio.motores import MOTOR_DEFECTO, MOTORES
        self.assertIn(MOTOR_DEFECTO, MOTORES)
        for clave, info in MOTORES.items():
            for campo in ("nombre", "comando", "continuar", "binario"):
                self.assertIn(campo, info, clave)
            self.assertEqual(info["comando"][0], info["binario"])
            self.assertEqual(info["continuar"][0], info["binario"])

    def test_cambiar_motor_actualiza_ventana(self):
        from estudio.motores import MOTORES
        from estudio.ventana import Ventana
        # programa inofensivo en vez de claude/opencode: no hace falta tenerlos instalados para esta prueba
        v = Ventana(["python", "-c", "import time; time.sleep(30)"])
        otro = next(c for c in MOTORES if c != v.motor)
        v._cambiar_motor(otro)
        self.assertEqual(v.motor, otro)
        self.assertTrue(v._acciones_motor[otro].isChecked())
        self.assertEqual(v.dock.windowTitle(), MOTORES[otro]["nombre"])
        self.assertEqual(v.ajustes.value("motor"), otro)
        v.terminal.cerrar()
        v.deleteLater()


@unittest.skipUnless(HAY_QT, "PySide6 no instalado")
class Vigia(unittest.TestCase):
    """El vigía central avisa de lo nuevo que deja Claude: subtítulos al momento, un vídeo cuando deja de crecer."""

    def test_novedades(self):
        from unittest import mock
        from nucleo import rutas
        import estudio.servicios as servicios
        a = app()
        with tempfile.TemporaryDirectory() as d:
            crudo, salida = os.path.join(d, "crudo"), os.path.join(d, "salida")
            with mock.patch.object(rutas, "CRUDO", crudo), mock.patch.object(servicios, "SALIDA", salida):
                v = servicios.Vigia()
                v._estable.setInterval(300)
                vistos = []
                v.novedad.connect(lambda t, r: vistos.append((t, os.path.basename(r))))
                archivos.escribir_json(os.path.join(salida, "s.subtitulos.json"), {"bloques": []})
                with open(os.path.join(salida, "short_X_editado.mp4"), "wb") as f:
                    f.write(b"x" * 1000)
                QTimer.singleShot(4000, a.quit)
                a.exec()
                v.deleteLater()
        self.assertIn(("subtitulos", "s.subtitulos.json"), vistos)
        self.assertIn(("resultado", "short_X_editado.mp4"), vistos)


class EstadoDeClaude(unittest.TestCase):
    """Hooks del proyecto (.claude/settings.json) -> estudio/hooks/estado_claude.py -> la app sabe en qué está Claude."""
    HOOK = os.path.join(REPO, "estudio", "hooks", "estado_claude.py")

    def _hook(self, estado, entrada, env_extra):
        import subprocess
        env = {k: v for k, v in os.environ.items() if k != "CUTLY_ESTADO_FICHERO"}
        env.update(env_extra)
        return subprocess.run([sys.executable, self.HOOK, estado], input=json.dumps(entrada), capture_output=True,
                              text=True, env=env, timeout=30)

    def test_escribe_el_estado_sin_imprimir_nada(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "estado.json")
            r = self._hook("necesita", {"hook_event_name": "Notification", "message": "permiso para Bash"},
                           {"CUTLY_ESTADO_FICHERO": f})
            self.assertEqual((r.returncode, r.stdout), (0, ""))     # lo impreso iría al contexto de Claude
            e = archivos.leer_json(f)
            self.assertEqual((e["estado"], e["mensaje"]), ("necesita", "permiso para Bash"))

    def test_fuera_de_la_app_no_hace_nada(self):
        r = self._hook("libre", {}, {})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_settings_del_proyecto(self):
        """Hooks que apuntan a un script que existe; permisos solo para herramientas del repo que existen."""
        s = archivos.leer_json(os.path.join(REPO, ".claude", "settings.json"))
        for evento in ("UserPromptSubmit", "PostToolUse", "Notification", "Stop"):
            orden = s["hooks"][evento][0]["hooks"][0]["command"]
            self.assertIn("estudio/hooks/estado_claude.py", orden)
            self.assertTrue(orden.rstrip().endswith("|| true"), "un hook nunca debe fallar")
        for regla in s["permissions"]["allow"]:
            for trozo in regla[5:-1].split():                     # Bash(python editor/x.py *) -> editor/x.py
                if trozo.endswith((".py", ".sh")):
                    self.assertTrue(os.path.exists(os.path.join(REPO, trozo)), regla)
            self.assertNotIn(regla, ("Bash(python *)", "Bash(bash *)", "Bash(*)"), "demasiado amplia")
        self.assertIn("Edit(/editor/videos-editados/_cortes.log)", s["permissions"]["ask"])   # nunca recrearlo
