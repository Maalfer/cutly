"""nucleo: audio, series, formato, transcripción (formatos), subtítulos (texto y tiempos)."""
import os
import tempfile
import unittest

import numpy as np

import util  # noqa: F401  (rutas)
from nucleo import audio, ffmpeg, formato, series, subtitulos, transcripcion
from nucleo.archivos import escribir_json
from nucleo.archivos import leer_texto as leer


def tono(seg, hz=16000, f=220, amp=0.3):
    t = np.arange(int(seg * hz)) / hz
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


class Audio(unittest.TestCase):
    def test_energia_distingue_voz_y_silencio(self):
        a = np.concatenate([np.zeros(16000, np.float32), tono(1.0)])
        rms, hf = audio.energia(a)
        self.assertEqual(len(rms), 200)                  # 2 s en ventanas de 10 ms
        self.assertLess(rms[:100].max(), -100)
        self.assertGreater(rms[100:].min(), -20)

    def test_mascara_quita_chasquidos_cortos(self):
        rms = np.full(100, -80.0)
        hf = np.full(100, -80.0)
        rms[10:13] = -20                                  # 30 ms: chasquido
        rms[50:80] = -20                                  # 300 ms: voz
        v = audio.mascara_voz(rms, hf)
        self.assertFalse(v[10:13].any())
        self.assertTrue(v[50:80].all())

    def test_mascara_respeta_sibilante_por_alta_frecuencia(self):
        rms = np.full(20, -60.0)
        hf = np.full(20, -80.0)
        hf[5:15] = -30                                    # "s" final: poco rms, mucha alta frecuencia
        self.assertTrue(audio.mascara_voz(rms, hf)[5:15].all())

    def test_filtro_normalizar_es_lineal(self):
        m = {"input_i": "-19", "input_tp": "-4", "input_lra": "5", "input_thresh": "-30", "target_offset": "0.1"}
        f = audio.filtro_normalizar(m, -14)
        self.assertIn("linear=true", f)
        self.assertIn("I=-14:TP=-1", f)


class SalidaAtomica(unittest.TestCase):
    """El vídeo final o está completo o no existe, y nunca quedan temporales sueltos (pasó: un reemplazo bloqueado
    dejó .tmp.mp4 y .tmp.mov de cientos de MB)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.dest = os.path.join(self.d, "short_X_editado.mp4")
        with open(self.dest, "w") as f:
            f.write("viejo")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

    def escribir(self, codigo=0):
        import sys
        return [sys.executable, "-c", f"import sys; open(sys.argv[1], 'w').write('nuevo'); sys.exit({codigo})"]

    def test_bien_reemplaza_y_sin_temporal(self):
        ffmpeg.salida_atomica(self.escribir(), self.dest, check=True)
        self.assertEqual(open(self.dest).read(), "nuevo")
        self.assertEqual(ffmpeg.temporales_de(self.dest), [])

    def test_fallo_deja_el_viejo_y_sin_temporal(self):
        import subprocess
        with self.assertRaises(subprocess.CalledProcessError):
            ffmpeg.salida_atomica(self.escribir(1), self.dest, check=True)
        self.assertEqual(open(self.dest).read(), "viejo")
        self.assertEqual(ffmpeg.temporales_de(self.dest), [])

    def test_destino_bloqueado_avisa_y_sin_temporal(self):
        from unittest import mock

        def bloqueado(origen, destino, **_kw):
            raise ffmpeg.ArchivoBloqueado("abierto")
        with mock.patch.object(ffmpeg, "reemplazar", bloqueado), self.assertRaises(ffmpeg.ArchivoBloqueado):
            ffmpeg.salida_atomica(self.escribir(), self.dest, check=True)
        self.assertEqual(open(self.dest).read(), "viejo")
        self.assertEqual(ffmpeg.temporales_de(self.dest), [])

    def test_reemplazar_reintenta_mientras_esta_bloqueado(self):
        from unittest import mock
        tmp = ffmpeg.ruta_temporal(self.dest)
        open(tmp, "w").write("nuevo")
        real, fallos = os.replace, [PermissionError(13, "abierto")] * 2
        with mock.patch.object(os, "replace", lambda a, b: real(a, b) if not fallos else (_ for _ in ()).throw(fallos.pop())):
            ffmpeg.reemplazar(tmp, self.dest, espera=5, cada=0.01)
        self.assertEqual(open(self.dest).read(), "nuevo")
        with mock.patch.object(os, "replace", side_effect=PermissionError(13, "abierto")),                 self.assertRaises(ffmpeg.ArchivoBloqueado):
            ffmpeg.reemplazar(tmp, self.dest, espera=0.05, cada=0.01)

    def test_nombres_de_temporales(self):
        self.assertEqual(ffmpeg.ruta_temporal("a/b.mp4"), "a/b.tmp.mp4")
        self.assertEqual(ffmpeg.ruta_temporal("a/b.mp4", ".mov"), "a/b.tmp.mov")


class Series(unittest.TestCase):
    def test_rachas(self):
        self.assertEqual(series.rachas([0, 1, 1, 0, 1], 1), [(1, 3), (4, 5)])
        self.assertEqual(series.rachas([1, 1, 0, 1], 0.5, minimo=0.6), [(0.0, 1.0)])


class Formato(unittest.TestCase):
    def test_lienzo(self):
        self.assertEqual(formato.BANDA_CARA + formato.ALTO_PANTALLA, formato.ALTO)
        # el recorte nativo llena exactamente la zona de pantalla al escalarlo a 1080 de ancho
        self.assertEqual(round(formato.RECORTE_H * formato.ANCHO / formato.RECORTE_W), formato.ALTO_PANTALLA)

    def test_cuantizar(self):
        self.assertAlmostEqual(formato.cuantizar(1.009), 1 + 1 / 60)


class Transcripcion(unittest.TestCase):
    def test_escribir_y_leer(self):
        segs = [{"start": 0.0, "end": 1.5, "text": "Hola qué tal", "words": [[0, 0.4, "Hola"], [0.5, 0.9, "qué"],
                                                                                [1.0, 1.5, " tal"]]}]
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "x")
            transcripcion.escribir(base, segs, "m", "cpu")
            self.assertEqual(transcripcion.cargar_segmentos(base + ".json"), segs)
            self.assertIn("00:00:01,500", leer(base + ".srt"))
            self.assertEqual(leer(base + ".txt"), "Hola qué tal\n")
        self.assertEqual(transcripcion.palabras(segs)[2], [1.0, 1.5, "tal"])

    def test_prompt_generico_con_vocabulario_del_glosario(self):
        p = transcripcion.prompt_subtitulos()
        self.assertIn("Vocabulario:", p)
        self.assertNotIn("4444", p)                       # nada de un vídeo concreto


class Subtitulos(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.glos = os.path.join(self.d.name, "g.json")
        escribir_json(self.glos, {"reemplazos": [[r"\bm[aá]quina (cal|kal)\b", "máquina Kali"],
                                                 [r"\breversell\b", "reverse shell"]]})

    def tearDown(self):
        self.d.cleanup()

    def test_glosario_por_frase_y_tiempos(self):
        ws = [[0, 0.5, "mi"], [0.5, 1.0, "máquina"], [1.0, 1.4, "cal."], [2.0, 3.0, "una"], [3.0, 4.0, "reversell"]]
        out = subtitulos.aplicar_glosario(ws, self.glos)
        self.assertEqual([w[2] for w in out], ["Mi", "máquina", "Kali.", "Una", "reverse", "shell"])
        self.assertEqual(out[4][0], 3.0)
        self.assertEqual(out[5][1], 4.0)                  # el tramo conserva sus límites

    def test_cal_suelto_no_se_toca(self):
        out = subtitulos.aplicar_glosario([[0, 1, "cal"], [1, 2, "viva"]], self.glos)
        self.assertEqual(out[0][2], "Cal")

    def test_agrupar_corta_tras_punto_y_por_longitud(self):
        ws = [[i * 0.3, i * 0.3 + 0.25, w] for i, w in enumerate("Hola. Esto es una frase bastante larga de prueba".split())]
        bl = subtitulos.agrupar(ws)
        self.assertEqual([w[2] for w in bl[0]], ["Hola."])
        self.assertTrue(all(len(" ".join(w[2] for w in b)) <= 28 for b in bl))
        self.assertTrue(all(len(b) <= 5 for b in bl))

    def test_linea_de_tiempo_sin_huecos_entre_bloques(self):
        """El parpadeo: entre dos bloques seguidos no puede haber un estado vacío."""
        bl = subtitulos.a_json([[[0.0, 0.3, "Hola"], [0.3, 0.6, "qué"]], [[0.7, 1.0, "tal"], [1.0, 1.3, "estás"]],
                                [[3.0, 3.4, "Adiós."]]])
        est = subtitulos.linea_de_tiempo(bl, 5.0)
        ts = [t for t, _ in est]
        self.assertEqual(ts, sorted(ts))
        vacios = [t for t, e in est[1:] if e is None]
        # solo se vacía tras la pausa larga (1,3 -> 3,0) y al final, nunca entre los bloques 1 y 2
        self.assertEqual(len(vacios), 2)
        self.assertAlmostEqual(vacios[0], 1.3 + 0.25)
        entra_2 = next(t for t, e in est if e and e[0] == 1)
        self.assertAlmostEqual(entra_2, 0.7 - 0.03)

    def test_texto_corregido_reparte_tiempos(self):
        bl = [{"palabras": [[0, 1, "reversell"]], "texto": "reverse shell"}]
        est = subtitulos.linea_de_tiempo(bl, 2.0)
        self.assertEqual(est[-2][1][1], ["reverse", "shell"])


if __name__ == "__main__":
    unittest.main()
