"""cutly estudio: interfaz de escritorio (PySide6) con el Claude Code INSTALADO dentro, con su interfaz completa.

    python -m estudio                 # sesión nueva de Claude Code en el repo
    python -m estudio --continuar     # retoma la última conversación (claude --continue)
    python -m estudio --comando powershell    # otro programa en el terminal (p. ej. para probar)

Requisitos: pip install -r requirements.txt · Claude Code instalado y con sesión iniciada (`claude` en el PATH).
"""
import argparse
import os
import sys

if __package__ in (None, ""):                         # también como `python estudio/__main__.py`
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    __package__ = "estudio"

from PySide6.QtCore import QCoreApplication, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import estudio.entorno  # noqa: E402,F401  (prepara las rutas de nucleo/ y vm/)


def main():
    ap = argparse.ArgumentParser(prog="python -m estudio", description="cutly estudio")
    ap.add_argument("--continuar", action="store_true", help="retomar la última conversación (claude --continue)")
    ap.add_argument("--comando", help="programa del terminal en vez de claude (p. ej. powershell)")
    ap.add_argument("--captura", nargs=2, metavar=("PNG", "SEG"),
                    help="diagnóstico: guarda una imagen de la ventana a los SEG segundos y cierra")
    ap.add_argument("--escribir", help="diagnóstico: texto que se envía a la sesión al arrancar (con Enter)")
    a = ap.parse_args()
    comando = a.comando.split() if a.comando else (["claude", "--continue"] if a.continuar else ["claude"])

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)   # requisito de QtWebEngine
    app = QApplication(sys.argv[:1])
    app.setApplicationName("cutly estudio")
    app.setOrganizationName("cutly")
    from estudio.ventana import Ventana
    v = Ventana(comando, app)
    v.show()
    if a.escribir:
        QTimer.singleShot(4000, lambda: v.enviar(a.escribir))
    if a.captura:
        png, seg = a.captura[0], float(a.captura[1])
        QTimer.singleShot(int(seg * 1000), lambda: (v.grab().save(png), v.close()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
