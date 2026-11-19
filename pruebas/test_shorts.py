"""editor/shorts: la lógica de cada herramienta, sin renderizar vídeo."""
import json
import os
import tempfile
import unittest

import numpy as np

from util import cargar

from nucleo.archivos import escribir_texto, leer_json

fusion = cargar("editor/shorts/fusionar_cara_pantalla.py")
sdt = cargar("editor/shorts/short_desde_toma.py")


class Apretar(unittest.TestCase):
    """Estilo del usuario: fuera toda pausa > 0,25 s; la pantalla sigue el mismo mapeo lineal (sincronía intacta)."""

    def voz(self, tramos_s, total=10.0):
        v = np.zeros(int(total * 100), bool)
        for a, b in tramos_s:
            v[int(a * 100):int(b * 100)] = True
        return v

    def test_parte_por_pausas_y_mantiene_mapeo(self):
        t = [{"a0": 0.0, "a1": 4.0, "abajo": "pant", "p0": 10.0, "p1": 18.0}]   # pantalla x2
        out = fusion.apretar(t, self.voz([(0.5, 1.5), (2.5, 3.5)]), 0.25, 0.04, 0.06)
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["a0"], 0.46)
        self.assertAlmostEqual(out[0]["a1"], 1.56)
        for p in out:                                     # mismo mapeo: p = 10 + 2*(a - 0)
            self.assertAlmostEqual(p["p0"], 10 + 2 * p["a0"])
            self.assertAlmostEqual(p["p1"], 10 + 2 * p["a1"])

    def test_tramo_sin_voz_desaparece(self):
        t = [{"a0": 5.0, "a1": 8.0, "abajo": "cara"}]
        self.assertEqual(fusion.apretar(t, self.voz([(0.5, 1.5)]), 0.25, 0.04, 0.06), [])

    def test_pausa_corta_no_parte(self):
        t = [{"a0": 0.0, "a1": 3.0, "abajo": "cara"}]
        self.assertEqual(len(fusion.apretar(t, self.voz([(0.5, 1.0), (1.2, 2.0)]), 0.25, 0.04, 0.06)), 1)


class ShortDesdeToma(unittest.TestCase):
    def test_fit_contain_nunca_recorta(self):
        self.assertEqual(sdt.fit_contain(960, 700, 1080, 1272), (1080, 788, 0))
        dw, dh, xoff = sdt.fit_contain(400, 1000, 1080, 1272)      # región alta: ajusta por el alto
        self.assertEqual(dh, 1272)
        self.assertEqual(xoff, (1080 - dw) // 2)

    def test_planos_region_letterbox_y_punto_recorte(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "t")
            ev = [{"op": "mark", "label": "A", "t_video": 0.0},
                  {"op": "focus", "args": [480, 500, 960, 700], "t_video": 0.5},
                  {"op": "mark", "label": "B", "t_video": 10.0},
                  {"op": "focus", "args": [1500, 400], "t_video": 10.5}]
            escribir_texto(base + ".steps.jsonl", "\n".join(json.dumps(e) for e in ev))
            marks, focos = sdt.cargar_registro(base)
        planos = sdt.planos_automaticos(marks, focos, 20.0, 1920, 1012, 8.0)
        self.assertEqual(len(planos), 4)                                  # cada acto de 10 s en 2 planos <= 8 s
        self.assertIn("rw", planos[1])                                    # región -> letterbox completo
        self.assertIn("cx0", planos[3])                                   # punto suelto -> recorte
        self.assertEqual(planos[1]["acto"], "A")


class Glosario(unittest.TestCase):
    def test_glosario_valido_y_general(self):
        from nucleo.rutas import GLOSARIO
        import re
        g = leer_json(GLOSARIO)
        for patron, bueno in g["reemplazos"]:
            re.compile(patron)
            self.assertTrue(bueno.strip())


if __name__ == "__main__":
    unittest.main()
