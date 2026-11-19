"""Un programa de terminal (Claude Code) corriendo en un pseudo-terminal REAL: ConPTY en Windows (pywinpty), pty en
macOS/Linux (ptyprocess). Para el programa es un terminal de verdad, así que muestra su interfaz completa.

    p = ProcesoPty(["claude"], cwd=REPO); p.salida.connect(...); p.iniciar(120, 40); p.escribir("hola\\r")

La salida se lee en un hilo y se entrega por la señal `salida` (Qt la pasa al hilo de la interfaz).
"""
import os
import shutil
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, Signal

if sys.platform == "win32":
    from winpty import PtyProcess
else:  # misma API
    from ptyprocess import PtyProcessUnicode as PtyProcess


def resolver(programa):
    """Ruta completa de un ejecutable del PATH (en Windows, con su extensión: claude.exe)."""
    ruta = shutil.which(programa)
    if not ruta:
        raise FileNotFoundError(f"no encuentro '{programa}' en el PATH")
    return ruta


class ProcesoPty(QObject):
    salida = Signal(str)          # texto que escribe el programa (con sus secuencias de escape)
    terminado = Signal(int)       # código de salida

    def __init__(self, argv, cwd=None, env=None, parent=None):
        super().__init__(parent)
        self.argv = [resolver(argv[0])] + list(argv[1:])
        self.cwd = cwd
        self.env = env
        self._p = None
        self._hilo = None

    def iniciar(self, columnas=120, filas=40):
        env = dict(os.environ if self.env is None else self.env)
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        if sys.platform == "win32":
            # pywinpty recibe la línea de órdenes como texto: comillas con las reglas de Windows
            argv = subprocess.list2cmdline(self.argv)
            self._p = PtyProcess.spawn(argv, cwd=self.cwd, env=env, dimensions=(filas, columnas))
        else:
            self._p = PtyProcess.spawn(self.argv, cwd=self.cwd, env=env, dimensions=(filas, columnas))
        self._hilo = threading.Thread(target=self._leer, daemon=True)
        self._hilo.start()

    def _leer(self):
        while True:
            try:
                datos = self._p.read(65536)
            except EOFError:
                break
            except Exception:
                if not self.vivo():
                    break
                continue
            if datos:
                self.salida.emit(datos)
            elif not self.vivo():
                break
        codigo = self._p.exitstatus if self._p.exitstatus is not None else -1
        self._liberar()
        self.terminado.emit(codigo)

    def _liberar(self):
        """Cierra el pseudo-terminal (pywinpty abre sockets internos que, si no, quedan abiertos)."""
        try:
            self._p.close()
        except Exception:
            pass

    def escribir(self, texto):
        if self.vivo():
            self._p.write(texto)

    def redimensionar(self, columnas, filas):
        if self.vivo() and columnas > 0 and filas > 0:
            self._p.setwinsize(filas, columnas)

    def vivo(self):
        return self._p is not None and self._p.isalive()

    def cerrar(self):
        if self.vivo():
            try:
                self._p.terminate(force=True)
            except Exception:
                pass
        if self._p is not None and (self._hilo is None or not self._hilo.is_alive()):
            self._liberar()
