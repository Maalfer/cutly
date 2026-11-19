"""La estructura no se degrada al crecer: dependencias en una sola dirección, CLIs vivas y documentación sin rutas
muertas."""
import glob
import os
import re
import subprocess
import sys
import unittest

from util import REPO

from nucleo.archivos import leer_texto as leer

SCRIPTS_PY = (glob.glob(os.path.join(REPO, "editor", "*", "*.py")) +
              [os.path.join(REPO, "editor", "comun", "transcribir.py")])
LOCALES = ("editor/crudo/", "editor/videos-editados/")    # material de cada vídeo: no está en git


class Dependencias(unittest.TestCase):
    def test_nucleo_no_depende_de_ninguna_linea(self):
        """nucleo/ es la base: no puede importar nada de editor/ ni de crear-shorts/."""
        for f in glob.glob(os.path.join(REPO, "nucleo", "*.py")):
            s = leer(f)
            self.assertNotRegex(s, r"(?m)^\s*(from|import)\s+(vm|vm_control|short_desde_toma|subtitular|tipear|mover)\b",
                                os.path.basename(f))

    def test_ningun_script_importa_otro_script(self):
        """Lo compartido va en nucleo/: un script no importa a otro (antes todos dependían de short_desde_toma)."""
        nombres = {os.path.splitext(os.path.basename(f))[0] for f in SCRIPTS_PY}
        for f in SCRIPTS_PY:
            s = leer(f)
            for n in nombres:
                self.assertNotRegex(s, rf"(?m)^\s*(from|import)\s+{n}\b", f"{os.path.basename(f)} importa {n}")


class Clis(unittest.TestCase):
    def test_help_de_cada_cli(self):
        for f in SCRIPTS_PY + [os.path.join(REPO, "crear-shorts", "herramientas", x) for x in ("tipear.py", "mover.py")]:
            if "construir_short" in f:          # plantilla, no CLI
                continue
            r = subprocess.run([sys.executable, f, "--help"], capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            self.assertEqual(r.returncode, 0, f"{os.path.relpath(f, REPO)}: {r.stderr[-300:]}")

    def test_vm_control_sin_argumentos_muestra_la_ayuda(self):
        r = subprocess.run([sys.executable, os.path.join(REPO, "crear-shorts", "herramientas", "vm_control.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertIn("CICLO DE VIDA", r.stdout + r.stderr)


class Documentacion(unittest.TestCase):
    def test_rutas_citadas_existen(self):
        """Toda ruta del repo citada entre `comillas` en un .md debe existir (salvo material local y ejemplos)."""
        muertas = []
        mds = [m for m in glob.glob(os.path.join(REPO, "**", "*.md"), recursive=True)
               if "historial" not in m and ".git" not in m]
        mds += glob.glob(os.path.join(REPO, ".claude", "skills", "*", "SKILL.md"))      # las skills también
        for md in mds:
            for tok in re.findall(r"`([^`\n]+)`", leer(md)):
                for palabra in tok.split():
                    p = palabra.strip("\"'(),;:")
                    if not re.match(r"^(editor|crear-shorts|nucleo|pruebas|estudio)/", p):
                        continue
                    if any(c in p for c in "<>*{}$") or p.startswith(LOCALES) or "..." in p or "…" in p:
                        continue
                    p = p.split("#")[0].rstrip("/.")
                    if not os.path.exists(os.path.join(REPO, p)):
                        muertas.append(f"{os.path.relpath(md, REPO)}: {p}")
        self.assertEqual(muertas, [], "rutas que no existen:\n" + "\n".join(muertas))

    def test_enlaces_markdown_relativos_existen(self):
        """[texto](ruta/relativa.md) resuelto desde la carpeta del propio .md."""
        muertos = []
        for md in glob.glob(os.path.join(REPO, "**", "*.md"), recursive=True):
            if ".git" in md:
                continue
            for destino in re.findall(r"\]\(([^)\s]+)\)", leer(md)):
                if re.match(r"^(https?:|mailto:|#)", destino):
                    continue
                ruta = os.path.normpath(os.path.join(os.path.dirname(md), destino.split("#")[0]))
                if not os.path.exists(ruta):
                    muertos.append(f"{os.path.relpath(md, REPO)}: {destino}")
        self.assertEqual(muertos, [], "enlaces rotos:\n" + "\n".join(muertos))


if __name__ == "__main__":
    unittest.main()
