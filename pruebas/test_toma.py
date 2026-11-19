"""Contrato Fase 1 -> Fase 2 (nucleo/toma.py): lo que escribe vm/ (registro de la toma) es exactamente lo que lee
editor/shorts/short_desde_toma.py. Se ejecuta el código real de los dos lados, sin VM."""
import os
import tempfile
import time
import unittest

from util import cargar

import vm_control as v
from vm import registro, toma as vm_toma

sdt = cargar("editor/shorts/short_desde_toma.py")


class Contrato(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.estado_orig = registro.STATE_FILE
        registro.STATE_FILE = os.path.join(self.d.name, "estado.json")     # no tocar una toma real abierta
        self.ruta_orig = vm_toma.contrato.ruta
        vm_toma.contrato.ruta = lambda n, ext: os.path.join(self.d.name, f"{n}.{ext}")
        self.crudo_orig = vm_toma.CRUDO
        vm_toma.CRUDO = self.d.name

    def tearDown(self):
        registro.STATE_FILE = self.estado_orig
        vm_toma.contrato.ruta = self.ruta_orig
        vm_toma.CRUDO = self.crudo_orig
        self.d.cleanup()

    def test_lo_que_escribe_la_fase_1_lo_entiende_la_fase_2(self):
        v.take_start("contrato")
        st = registro._state()
        st["rec_t0"] = time.time() - 5.0                                    # como si la grabación llevara 5 s
        registro._save_state(st)
        v.mark("Acto 1: recon")
        v.focus(480, 500, "terminal", 960, 700)
        v.focus(1500, 400, "resultado")
        st = registro._state()
        st.pop("rec_t0")
        registro._save_state(st)
        v.take_end()

        base = os.path.join(self.d.name, "contrato")
        self.assertTrue(os.path.exists(base + ".mapa.md"))
        marks, focos = sdt.cargar_registro(base)
        self.assertEqual([m[1] for m in marks], ["Acto 1: recon"])
        self.assertAlmostEqual(marks[0][0], 5.0, delta=0.5)                # t_video: s desde el inicio del vídeo
        self.assertEqual([f[1:] for f in focos], [(480, 500, 960, 700), (1500, 400, None, None)])


if __name__ == "__main__":
    unittest.main()
