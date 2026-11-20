"""cutly estudio: interfaz de escritorio (PySide6) con Claude Code u OpenCode INSTALADOS dentro, con su interfaz
completa (Sesión → Motor elige cuál; estudio/motores.py).

    python -m estudio                 # sesión nueva, con el último motor elegido (Claude Code por defecto)
    python -m estudio --continuar     # retoma la última conversación de ESE motor (--continue)
    python -m estudio --comando powershell    # otro programa en el terminal (p. ej. para probar)

Requisitos: pip install -r requirements.txt · Claude Code y/o OpenCode instalados y con sesión iniciada
(`claude` y/o `opencode` en el PATH).
"""
import argparse
import os
import sys

if __package__ in (None, ""):                         # también como `python estudio/__main__.py`
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    __package__ = "estudio"

from PySide6.QtCore import QCoreApplication, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import estudio.entorno  # noqa: E402  (prepara las rutas de nucleo/ y vm/)


def main():
    ap = argparse.ArgumentParser(prog="python -m estudio", description="cutly estudio")
    ap.add_argument("--continuar", action="store_true", help="retomar la última conversación del motor elegido (--continue)")
    ap.add_argument("--comando", help="programa del terminal en vez del motor elegido (p. ej. powershell, para probar)")
    ap.add_argument("--captura", nargs=2, metavar=("PNG", "SEG"),
                    help="diagnóstico: guarda una imagen de la ventana a los SEG segundos y cierra")
    ap.add_argument("--escribir", help="diagnóstico: texto que se envía a la sesión al arrancar (con Enter)")
    a = ap.parse_args()
    comando = a.comando.split() if a.comando else None   # None: Ventana resuelve el motor elegido (Sesión → Motor)

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)   # requisito de QtWebEngine
    app = QApplication(sys.argv[:1])
    app.setApplicationName("cutly estudio")
    app.setOrganizationName("cutly")
    app.setWindowIcon(QIcon(estudio.entorno.LOGO))   # icono de la app: ventana, barra de tareas, alt-tab
    from estudio.ventana import Ventana
    v = Ventana(comando, app, continuar=a.continuar)
    v.show()
    if a.escribir:
        QTimer.singleShot(4000, lambda: v.enviar(a.escribir))
    if a.captura:
        png, seg = a.captura[0], float(a.captura[1])
        QTimer.singleShot(int(seg * 1000), lambda: (v.grab().save(png), v.close()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
