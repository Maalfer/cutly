"""Rutas y utilidades comunes de la app: importa nucleo/ y el paquete vm/ del repo, ejecuta en segundo plano sin
congelar la ventana y lanza las CLIs del repo mostrando su salida en directo.

La app NO duplica lógica: lee con nucleo/ y vm/, y todo lo que modifica algo lo hacen las CLIs del repo o Claude Code.
"""
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HERRAMIENTAS = os.path.join(REPO, "crear-shorts", "herramientas")
for _p in (REPO, HERRAMIENTAS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QRunnable, QThreadPool, Signal  # noqa: E402

VM_CONTROL = os.path.join(HERRAMIENTAS, "vm_control.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class _Emisor(QObject):
    hecho = Signal(object)
    fallo = Signal(str)


class _Tarea(QRunnable):
    def __init__(self, fn, emisor):
        super().__init__()
        self.fn, self.emisor = fn, emisor

    def run(self):
        try:
            self.emisor.hecho.emit(self.fn())
        except BaseException as e:          # incluye SystemExit de die(): se muestra, no tumba la app
            self.emisor.fallo.emit(str(e))


_VIVOS = set()       # emisores de tareas en curso: si Python los liberase antes de acabar, Qt perdería la señal


def en_segundo_plano(fn, al_terminar, al_fallar=None):
    """Ejecuta fn() en el pool de hilos de Qt y entrega el resultado en el hilo de la interfaz."""
    e = _Emisor()
    _VIVOS.add(e)
    e.hecho.connect(al_terminar)
    if al_fallar:
        e.fallo.connect(al_fallar)
    e.hecho.connect(lambda _r: _VIVOS.discard(e))
    e.fallo.connect(lambda _m: _VIVOS.discard(e))
    QThreadPool.globalInstance().start(_Tarea(fn, e))
    return e


def ejecutar_cli(argv, salida, al_terminar=None, parent=None, env_extra=None):
    """Lanza `python <argv...>` en el repo con QProcess y va escribiendo su salida (sin colores ANSI) en `salida`
    (un QPlainTextEdit). Devuelve el QProcess."""
    p = QProcess(parent)
    p.setWorkingDirectory(REPO)
    p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONUTF8", "1")
    env.insert("PYTHONIOENCODING", "utf-8")
    for k, v in (env_extra or {}).items():
        env.insert(k, v)
    p.setProcessEnvironment(env)

    def leer():
        texto = bytes(p.readAll()).decode("utf-8", "replace")
        salida.appendPlainText(ANSI.sub("", texto).rstrip("\n"))

    p.readyRead.connect(leer)
    if al_terminar:
        p.finished.connect(lambda codigo, _estado: al_terminar(codigo))
    salida.appendPlainText(f"$ python {' '.join(os.path.relpath(a, REPO) if os.path.isabs(a) else a for a in argv)}")
    p.start(sys.executable, argv)
    return p
