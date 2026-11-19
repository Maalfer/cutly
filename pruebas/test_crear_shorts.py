"""crear-shorts: lógica pura de la entrada humana y el paquete vm (sin VM: nada aquí habla con VirtualBox)."""
import random
import unittest

import util  # noqa: F401  (rutas)
import mover
import ocr_buscar
import tipear
import vm_control as v


class EntradaHumana(unittest.TestCase):
    def test_tipear_escribe_el_texto_aunque_haya_errores(self):
        ev = tipear.plan("nmap -p- 172.17.0.2", 45, 0.2, random.Random(3))
        texto = []
        for e in ev:
            if e[0] == "k":
                texto.append(e[1])
            elif e[0] == "bs":
                texto.pop()
        self.assertEqual("".join(texto), "nmap -p- 172.17.0.2")

    def test_tipear_reproducible_con_semilla(self):
        self.assertEqual(tipear.plan("hola", rng=random.Random(1)), tipear.plan("hola", rng=random.Random(1)))

    def test_trayecto_llega_al_destino(self):
        pts = mover.trayecto(10, 10, 900, 500, rng=random.Random(2))
        self.assertEqual(tuple(pts[-1]), (900, 500))
        self.assertGreater(len(pts), 5)

    def test_compile_plan_linea_de_tiempo(self):
        ev = v.compile_plan([("k", "a"), ("d", 0.1), ("k", "ñ"), ("ret",), ("m", 5, 6)])
        self.assertEqual([e["t"] for e in ev], [0.0, 0.1, 0.1, 0.1])
        self.assertEqual(ev[1]["delay"], 40)              # no ASCII: delay >= 30 ms o se pierde el carácter
        self.assertEqual(ev[2]["name"], "Return")


class Ocr(unittest.TestCase):
    LINEAS = ["Intercept\t[100,50 80x20]\n", "Intercept\t[400,300 80x20]\n", "/cuenta?id=1001\t[10,400 150x20]\n"]

    def test_n_esima_y_ultima(self):
        self.assertEqual(ocr_buscar.buscar(self.LINEAS, "intercept", 1, 1.0, None, "", "exacta"), "140,60")
        self.assertEqual(ocr_buscar.buscar(self.LINEAS, "intercept", -1, 1.0, None, "", "exacta"), "440,310")

    def test_region_y_subcadena(self):
        self.assertEqual(ocr_buscar.buscar(self.LINEAS, "intercept", 1, 1.0, (300, 200, 400, 300), "", "exacta"),
                         "440,310")
        r = ocr_buscar.buscar(self.LINEAS, "1001", 1, 1.0, None, "1001", "contiene")
        self.assertGreater(int(r.split(",")[0]), 110)    # apunta al trozo, no al centro de la palabra


class PaqueteVm(unittest.TestCase):
    def test_api_que_usan_las_demos(self):
        for n in ("_words_text activate activate_id clicktext die focus labcheck launch_terminal mark place_id prepare "
                  "rec_start selecttext ssh take_end take_start type_human type_in typeurl waitfor waitstill").split():
            self.assertTrue(hasattr(v, n), n)


if __name__ == "__main__":
    unittest.main()
